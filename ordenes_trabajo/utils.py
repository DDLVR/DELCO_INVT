"""
Utilidades para órdenes de trabajo: importación masiva, exportación,
detección de duplicados e integración con informes de clientes.
"""
import json
import os
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import openpyxl
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from clientes.models import Cliente
from importaciones.models import ImportacionExcel, ImportacionExcelError
from usuarios.models import Usuario

from .models import InformeCliente, OrdenTrabajo

DIAS_ALERTA_DUPLICADO = 14

TIPO_TRABAJO_MAP = {
    'INSTALACION': 'INSTALACION',
    'INSTALACIÓN': 'INSTALACION',
    'INSTALACION MEDIDOR': 'INSTALACION',
    'CAMBIO': 'CAMBIO',
    'CAMBIO DE EQUIPO': 'CAMBIO',
    'RETIRO': 'RETIRO',
    'MANTENCION': 'MANTENCION',
    'MANTENCIÓN': 'MANTENCION',
    'MANTENIMIENTO': 'MANTENCION',
    'REPARACION': 'REPARACION',
    'REPARACIÓN': 'REPARACION',
    'INSPECCION': 'INSPECCION',
    'INSPECCIÓN': 'INSPECCION',
    'CONFIGURACION': 'CONFIGURACION',
    'CONFIGURACIÓN': 'CONFIGURACION',
    'OTRO': 'OTRO',
}

COLUMNAS_ORDEN = {
    'numero_cliente': (
        'numero_cliente', 'numero cliente', 'n cliente', 'cliente', 'n° cliente',
        'nº cliente', 'id cliente',
    ),
    'titulo': ('titulo', 'título', 'titulo trabajo', 'asunto'),
    'descripcion': ('descripcion', 'descripción', 'detalle', 'observaciones'),
    'tipo_trabajo': ('tipo_trabajo', 'tipo trabajo', 'tipo', 'actividad', 'trabajo'),
    'tecnico': (
        'tecnico', 'técnico', 'responsable', 'tecnico responsable',
        'técnico responsable', 'asignado a',
    ),
    'fecha_trabajo': ('fecha', 'fecha trabajo', 'fecha asignacion', 'fecha asignación'),
}


def _normalizar_texto(valor) -> str:
    if valor is None:
        return ''
    return str(valor).strip()


def _mapear_headers(headers) -> Dict[str, int]:
    indice = {}
    for i, header in enumerate(headers):
        if header is None:
            continue
        clave = _normalizar_texto(header).lower()
        for campo, alias in COLUMNAS_ORDEN.items():
            if clave in alias and campo not in indice:
                indice[campo] = i
    return indice


def _valor_fila(valores, indice, campo, default=''):
    pos = indice.get(campo)
    if pos is None or pos >= len(valores):
        return default
    return _normalizar_texto(valores[pos])


def _resolver_tipo_trabajo(texto: str) -> str:
    clave = _normalizar_texto(texto).upper()
    if not clave:
        return 'INSTALACION'
    if clave in dict(OrdenTrabajo.TIPO_TRABAJO_CHOICES):
        return clave
    return TIPO_TRABAJO_MAP.get(clave, 'OTRO')


def _resolver_tecnico(texto: str) -> Optional[Usuario]:
    nombre = _normalizar_texto(texto)
    if not nombre:
        return None
    tecnico = Usuario.objects.filter(rol='TECNICO', is_active=True, nombre_interno__iexact=nombre).first()
    if tecnico:
        return tecnico
    return Usuario.objects.filter(rol='TECNICO', is_active=True, username__iexact=nombre).first()


def _fila_a_texto(headers, valores):
    data = {}
    for i, valor in enumerate(valores):
        nombre = headers[i] if i < len(headers) else f'Columna_{i + 1}'
        data[str(nombre)] = valor
    return json.dumps(data, ensure_ascii=False, default=str)


def detectar_duplicado_orden(
    cliente,
    exclude_orden_id=None,
    dias: int = DIAS_ALERTA_DUPLICADO,
) -> Tuple[bool, str]:
    """
    Alerta si existe otra orden activa/reciente para el mismo cliente
    dentro de la ventana configurada (14 días por defecto).
    """
    if not cliente:
        return False, ''

    desde = timezone.now() - timedelta(days=dias)
    estados_relevantes = list(OrdenTrabajo.ESTADOS_ABIERTOS) + [
        'REALIZADA',
        'REALIZADA_PENDIENTE_COMPROBACION',
        'PENDIENTE_VALIDACION',
    ]

    qs = OrdenTrabajo.objects.filter(
        cliente=cliente,
        fecha_creacion__gte=desde,
        estado__in=estados_relevantes,
    ).exclude(estado='CANCELADA')

    if exclude_orden_id:
        qs = qs.exclude(pk=exclude_orden_id)

    anterior = qs.order_by('-fecha_creacion').first()
    if not anterior:
        return False, ''

    dias_diff = (timezone.now() - anterior.fecha_creacion).days
    desc = (
        f'Posible trabajo duplicado — Cliente: {cliente.numero_cliente} | '
        f'Orden anterior: #{anterior.id} ({anterior.get_estado_display()}) | '
        f'Creada: {anterior.fecha_creacion.strftime("%d/%m/%Y %H:%M")} | '
        f'Hace {dias_diff} día(s) (ventana: {dias} días)'
    )
    return True, desc


def aplicar_alerta_duplicado(orden: OrdenTrabajo) -> None:
    if not orden.cliente_id:
        return
    tiene_alerta, desc = detectar_duplicado_orden(orden.cliente, exclude_orden_id=orden.pk)
    if tiene_alerta:
        orden.alerta_duplicado = True
        orden.descripcion_alerta_duplicado = desc
        orden.save(update_fields=['alerta_duplicado', 'descripcion_alerta_duplicado'])


def importar_ordenes_excel(archivo, usuario) -> ImportacionExcel:
    importacion = ImportacionExcel.objects.create(
        tipo='ORDENES_TRABAJO',
        archivo_original=getattr(archivo, 'name', 'Upload'),
        usuario=usuario,
    )

    try:
        wb = openpyxl.load_workbook(archivo)
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        indice = _mapear_headers(headers)

        if 'numero_cliente' not in indice:
            raise ValueError(
                'El Excel debe incluir la columna "Numero Cliente" (o "Cliente").'
            )

        contador = 0
        exitosas = 0
        fallidas = 0
        alertas = 0

        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=False), start=2):
            valores = [cell.value for cell in row]
            if not any(valores):
                continue

            contador += 1
            try:
                numero_cliente = _valor_fila(valores, indice, 'numero_cliente')
                if not numero_cliente:
                    raise ValueError('Numero Cliente es obligatorio')

                cliente = Cliente.objects.filter(numero_cliente=numero_cliente).first()
                if not cliente:
                    cliente = Cliente.objects.create(
                        numero_cliente=numero_cliente,
                        direccion=f'Cliente {numero_cliente}',
                        comuna='Por definir',
                    )

                titulo = _valor_fila(valores, indice, 'titulo') or f'Trabajo — {numero_cliente}'
                descripcion = _valor_fila(valores, indice, 'descripcion')
                tipo_trabajo = _resolver_tipo_trabajo(_valor_fila(valores, indice, 'tipo_trabajo'))
                tecnico = _resolver_tecnico(_valor_fila(valores, indice, 'tecnico'))

                with transaction.atomic():
                    orden = OrdenTrabajo(
                        titulo=titulo,
                        descripcion=descripcion,
                        tipo_trabajo=tipo_trabajo,
                        cliente=cliente,
                        creada_por=usuario,
                        estado='CREADA',
                    )
                    if tecnico:
                        orden.tecnico_responsable = tecnico
                        orden.estado = 'ASIGNADA'
                        orden.fecha_asignacion = timezone.now()
                    orden.save()
                    aplicar_alerta_duplicado(orden)
                    if orden.alerta_duplicado:
                        alertas += 1

                exitosas += 1
            except Exception as exc:
                fallidas += 1
                ImportacionExcelError.objects.create(
                    importacion=importacion,
                    numero_fila=idx,
                    motivo=str(exc),
                    data_cruda=_fila_a_texto(headers, valores),
                )

        importacion.total_filas = contador
        importacion.exitosas = exitosas
        importacion.fallidas = fallidas
        importacion.estado = 'COMPLETADO'
        importacion.observaciones = (
            f'Se importaron {exitosas} de {contador} órdenes. '
            f'Alertas duplicidad: {alertas}. Fallidas: {fallidas}.'
        )
        importacion.save()
    except Exception as exc:
        importacion.estado = 'ERROR'
        importacion.observaciones = f'Error en importación: {exc}'
        importacion.save()

    return importacion


def exportar_ordenes_excel(queryset) -> BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Ordenes de Trabajo'
    ws.append([
        'ID', 'Titulo', 'Tipo Trabajo', 'Estado', 'Numero Cliente',
        'Tecnico Responsable', 'Fecha Creacion', 'Fecha Asignacion',
        'Alerta Duplicado', 'Descripcion Alerta',
    ])

    for orden in queryset.select_related('cliente', 'tecnico_responsable'):
        ws.append([
            orden.id,
            orden.titulo,
            orden.get_tipo_trabajo_display(),
            orden.get_estado_display(),
            orden.cliente.numero_cliente if orden.cliente else '',
            orden.tecnico_responsable.nombre_interno if orden.tecnico_responsable else '',
            orden.fecha_creacion.strftime('%d/%m/%Y %H:%M') if orden.fecha_creacion else '',
            orden.fecha_asignacion.strftime('%d/%m/%Y %H:%M') if orden.fecha_asignacion else '',
            'SI' if orden.alerta_duplicado else 'NO',
            orden.descripcion_alerta_duplicado,
        ])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def guardar_informe_pdf(
    cliente,
    archivo_origen,
    nombre_archivo: str,
    orden=None,
    usuario=None,
    origen: str = 'MANUAL',
    registro_moreapp=None,
) -> InformeCliente:
    """Guarda un PDF en Registros/Evidencias."""
    Path(settings.EVIDENCIAS_ROOT).mkdir(parents=True, exist_ok=True)

    informe = InformeCliente(
        orden=orden,
        cliente=cliente,
        nombre_archivo=nombre_archivo,
        subido_por=usuario,
        origen=origen,
        registro_moreapp=registro_moreapp,
    )

    if hasattr(archivo_origen, 'read'):
        informe.archivo.save(nombre_archivo, archivo_origen, save=False)
    elif isinstance(archivo_origen, (bytes, bytearray)):
        informe.archivo.save(nombre_archivo, ContentFile(archivo_origen), save=False)
    elif isinstance(archivo_origen, str) and os.path.isfile(archivo_origen):
        with open(archivo_origen, 'rb') as fh:
            informe.archivo.save(nombre_archivo, ContentFile(fh.read()), save=False)
    else:
        raise ValueError('Origen de archivo PDF no válido')

    informe.save()
    return informe


def _buscar_pdfs_en_carpeta(ruta_carpeta: str):
    if not ruta_carpeta or not os.path.isdir(ruta_carpeta):
        return []
    return [
        os.path.join(ruta_carpeta, nombre)
        for nombre in os.listdir(ruta_carpeta)
        if nombre.lower().endswith('.pdf')
    ]


def vincular_informe_cliente_a_orden(
    cliente,
    registro_moreapp=None,
    ruta_carpeta: Optional[str] = None,
    usuario=None,
) -> Optional[OrdenTrabajo]:
    """
    Cuando llega un informe con número de cliente, marca la orden abierta
    como REALIZADA_PENDIENTE_COMPROBACION y guarda PDFs encontrados.
    """
    if not cliente:
        return None

    orden = OrdenTrabajo.objects.filter(
        cliente=cliente,
        estado__in=list(OrdenTrabajo.ESTADOS_ABIERTOS) + ['REALIZADA'],
    ).order_by('-fecha_creacion').first()

    if orden and orden.estado != 'REALIZADA_PENDIENTE_COMPROBACION':
        orden.estado = 'REALIZADA_PENDIENTE_COMPROBACION'
        if not orden.fecha_fin_ejecucion:
            orden.fecha_fin_ejecucion = timezone.now()
        orden.save(update_fields=['estado', 'fecha_fin_ejecucion'])

    if registro_moreapp:
        registro_moreapp.orden = orden
        registro_moreapp.save(update_fields=['orden'])

    pdfs = _buscar_pdfs_en_carpeta(ruta_carpeta or '')
    for pdf_path in pdfs:
        nombre = os.path.basename(pdf_path)
        if InformeCliente.objects.filter(
            cliente=cliente,
            nombre_archivo=nombre,
            registro_moreapp=registro_moreapp,
        ).exists():
            continue
        guardar_informe_pdf(
            cliente=cliente,
            archivo_origen=pdf_path,
            nombre_archivo=nombre,
            orden=orden,
            usuario=usuario,
            origen='MOREAPP' if registro_moreapp else 'SISTEMA',
            registro_moreapp=registro_moreapp,
        )

    return orden


def asignar_ordenes_masivo(ids, tecnico_id, usuario) -> Dict[str, Any]:
    tecnico = Usuario.objects.get(pk=tecnico_id, rol='TECNICO', is_active=True)
    ordenes = OrdenTrabajo.objects.filter(pk__in=ids)
    actualizadas = 0
    alertas = 0

    for orden in ordenes:
        orden.tecnico_responsable = tecnico
        orden.estado = 'ASIGNADA'
        orden.fecha_asignacion = timezone.now()
        orden.save(update_fields=['tecnico_responsable', 'estado', 'fecha_asignacion'])
        aplicar_alerta_duplicado(orden)
        if orden.alerta_duplicado:
            alertas += 1
        actualizadas += 1

    return {
        'actualizadas': actualizadas,
        'alertas_duplicado': alertas,
        'tecnico': tecnico.nombre_interno,
    }
