"""
Utilidades para órdenes de trabajo: importación masiva, exportación,
detección de duplicados e integración con informes de clientes.
"""
import json
import os
import unicodedata
from datetime import timedelta
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

ESTADO_MAP = {
    codigo: codigo for codigo, _ in OrdenTrabajo.ESTADO_CHOICES
}
for codigo, etiqueta in OrdenTrabajo.ESTADO_CHOICES:
    ESTADO_MAP[etiqueta.upper()] = codigo
    clave = unicodedata.normalize('NFD', etiqueta.upper())
    clave = ''.join(c for c in clave if unicodedata.category(c) != 'Mn')
    ESTADO_MAP[clave] = codigo

# Columnas reconocidas al importar (compatible con el Excel que genera exportar_ordenes_excel)
COLUMNAS_ORDEN = {
    'numero_cliente': (
        'numero_cliente', 'numero cliente', 'n cliente', 'cliente', 'n° cliente',
        'nº cliente', 'id cliente',
    ),
    'titulo': ('titulo', 'título', 'titulo trabajo', 'asunto'),
    'descripcion': ('descripcion', 'descripción', 'detalle'),
    'tipo_trabajo': ('tipo_trabajo', 'tipo trabajo', 'tipo', 'actividad', 'trabajo'),
    'tecnico': (
        'tecnico', 'técnico', 'responsable', 'tecnico responsable',
        'tecnico_responsable', 'técnico responsable', 'asignado a',
    ),
    'estado': ('estado',),
    'observaciones_tecnicas': ('observaciones tecnicas', 'observaciones_tecnicas'),
    'id_orden': ('id orden', 'id_orden'),
    'direccion_cliente': ('direccion cliente', 'direccion_cliente', 'direccion'),
    'comuna': ('comuna',),
    'fecha_trabajo': ('fecha', 'fecha trabajo', 'fecha asignacion', 'fecha asignación'),
}


def _normalizar_texto(valor) -> str:
    if valor is None:
        return ''
    if isinstance(valor, bool):
        return 'Si' if valor else 'No'
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        if valor.is_integer():
            return str(int(valor))
        return str(valor).strip()
    texto = str(valor).strip()
    if texto.endswith('.0'):
        base = texto[:-2]
        if base.isdigit():
            return base
    return texto


def _limpiar_header(texto) -> str:
    clave = _normalizar_texto(texto).lower()
    if clave.startswith('\ufeff'):
        clave = clave.lstrip('\ufeff')
    clave = unicodedata.normalize('NFD', clave)
    return ''.join(c for c in clave if unicodedata.category(c) != 'Mn')


def _variantes_header(clave: str):
    variantes = {clave}
    variantes.add(clave.replace(' ', '_'))
    variantes.add(clave.replace('_', ' '))
    return variantes


def _mapear_headers(headers) -> Dict[str, int]:
    indice = {}
    for i, header in enumerate(headers):
        if header is None:
            continue
        clave_base = _limpiar_header(header)
        for campo, alias in COLUMNAS_ORDEN.items():
            if campo in indice:
                continue
            for variante in _variantes_header(clave_base):
                if variante in alias:
                    indice[campo] = i
                    break
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
    clave_sin_acentos = unicodedata.normalize('NFD', clave)
    clave_sin_acentos = ''.join(c for c in clave_sin_acentos if unicodedata.category(c) != 'Mn')
    if clave in dict(OrdenTrabajo.TIPO_TRABAJO_CHOICES):
        return clave
    if clave_sin_acentos in dict(OrdenTrabajo.TIPO_TRABAJO_CHOICES):
        return clave_sin_acentos
    return TIPO_TRABAJO_MAP.get(clave, TIPO_TRABAJO_MAP.get(clave_sin_acentos, 'OTRO'))


def _resolver_estado(texto: str) -> Optional[str]:
    clave = _normalizar_texto(texto).upper()
    if not clave:
        return None
    clave_sin_acentos = unicodedata.normalize('NFD', clave)
    clave_sin_acentos = ''.join(c for c in clave_sin_acentos if unicodedata.category(c) != 'Mn')
    return ESTADO_MAP.get(clave) or ESTADO_MAP.get(clave_sin_acentos)


def _parse_id_orden(valor) -> Optional[int]:
    texto = _normalizar_texto(valor)
    if not texto:
        return None
    try:
        return int(float(texto))
    except (ValueError, TypeError):
        return None


def _resolver_tecnico(texto: str) -> Optional[Usuario]:
    """Busca técnico por nombre_interno, nombre, email o RUT. Nunca lanza error."""
    nombre = _normalizar_texto(texto)
    if not nombre:
        return None
    qs = Usuario.objects.filter(rol='TECNICO', is_active=True)
    for lookup in (
        {'nombre_interno__iexact': nombre},
        {'nombre__iexact': nombre},
        {'email__iexact': nombre},
        {'rut__iexact': nombre},
    ):
        tecnico = qs.filter(**lookup).first()
        if tecnico:
            return tecnico
    return None


def _obtener_o_crear_cliente(numero_cliente: str, valores, indice) -> Cliente:
    cliente = Cliente.objects.filter(numero_cliente=numero_cliente).first()
    if not cliente:
        cliente = Cliente.objects.filter(numero_cliente__iexact=numero_cliente).first()
    if cliente:
        return cliente

    direccion = _valor_fila(valores, indice, 'direccion_cliente') or f'Cliente {numero_cliente}'
    comuna = _valor_fila(valores, indice, 'comuna') or 'Por definir'
    cliente, _ = Cliente.objects.get_or_create(
        numero_cliente=numero_cliente,
        defaults={'direccion': direccion, 'comuna': comuna},
    )
    return cliente


def _aplicar_tecnico_a_orden(orden: OrdenTrabajo, tecnico: Optional[Usuario]) -> None:
    if tecnico:
        orden.tecnico_responsable = tecnico
        if orden.estado == 'CREADA':
            orden.estado = 'ASIGNADA'
            if not orden.fecha_asignacion:
                orden.fecha_asignacion = timezone.now()


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
        nombre_archivo = getattr(archivo, 'name', '') or ''
        if nombre_archivo.lower().endswith('.xls') and not nombre_archivo.lower().endswith('.xlsx'):
            raise ValueError(
                'Formato .xls no soportado. Guarda el archivo como Excel (.xlsx) e intenta de nuevo.'
            )

        if hasattr(archivo, 'seek'):
            archivo.seek(0)
        wb = openpyxl.load_workbook(archivo, data_only=True)
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        indice = _mapear_headers(headers)

        if 'numero_cliente' not in indice:
            raise ValueError(
                'El Excel debe incluir la columna "Numero Cliente" (o "Cliente"). '
                f'Columnas detectadas: {", ".join(str(h) for h in headers if h)}'
            )

        contador = 0
        exitosas = 0
        fallidas = 0
        alertas = 0
        creadas = 0
        actualizadas = 0

        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=False), start=2):
            valores = [cell.value for cell in row]
            if not any(v is not None and str(v).strip() != '' for v in valores):
                continue

            numero_cliente_raw = _valor_fila(valores, indice, 'numero_cliente')
            if numero_cliente_raw and _limpiar_header(numero_cliente_raw) in COLUMNAS_ORDEN['numero_cliente']:
                continue

            contador += 1
            try:
                numero_cliente = numero_cliente_raw
                if not numero_cliente:
                    raise ValueError('Numero Cliente es obligatorio')

                cliente = _obtener_o_crear_cliente(numero_cliente, valores, indice)

                titulo = _valor_fila(valores, indice, 'titulo') or f'Trabajo — {numero_cliente}'
                descripcion = _valor_fila(valores, indice, 'descripcion')
                tipo_trabajo = _resolver_tipo_trabajo(_valor_fila(valores, indice, 'tipo_trabajo'))
                tecnico_nombre = _valor_fila(valores, indice, 'tecnico')
                tecnico = _resolver_tecnico(tecnico_nombre)
                estado_import = _resolver_estado(_valor_fila(valores, indice, 'estado'))
                observaciones_tecnicas = _valor_fila(valores, indice, 'observaciones_tecnicas')
                orden_id = _parse_id_orden(_valor_fila(valores, indice, 'id_orden'))

                with transaction.atomic():
                    orden = None
                    if orden_id:
                        orden = OrdenTrabajo.objects.filter(pk=orden_id).first()

                    if orden:
                        orden.cliente = cliente
                        orden.titulo = titulo[:200]
                        orden.descripcion = descripcion
                        orden.tipo_trabajo = tipo_trabajo
                        if observaciones_tecnicas:
                            orden.observaciones_tecnicas = observaciones_tecnicas
                        if estado_import:
                            orden.estado = estado_import
                        if tecnico:
                            _aplicar_tecnico_a_orden(orden, tecnico)
                        elif not tecnico_nombre:
                            pass
                        orden.save()
                        actualizadas += 1
                    else:
                        orden = OrdenTrabajo(
                            titulo=titulo[:200],
                            descripcion=descripcion,
                            tipo_trabajo=tipo_trabajo,
                            cliente=cliente,
                            creada_por=usuario,
                            estado='CREADA',
                        )
                        if observaciones_tecnicas:
                            orden.observaciones_tecnicas = observaciones_tecnicas
                        if estado_import and estado_import != 'CREADA':
                            orden.estado = estado_import
                        if tecnico:
                            _aplicar_tecnico_a_orden(orden, tecnico)
                        orden.save()
                        creadas += 1

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
        importacion.estado = 'COMPLETADO' if contador > 0 and exitosas > 0 else ('ERROR' if contador == 0 else 'COMPLETADO')
        if contador == 0:
            importacion.observaciones = 'No se encontraron filas con datos para importar.'
        else:
            importacion.observaciones = (
                f'Se procesaron {exitosas} de {contador} filas '
                f'(creadas: {creadas}, actualizadas: {actualizadas}). '
                f'Alertas duplicidad: {alertas}. Fallidas: {fallidas}.'
            )
        importacion.save()
    except Exception as exc:
        importacion.estado = 'ERROR'
        importacion.observaciones = f'Error en importación: {exc}'
        importacion.save()

    return importacion


def exportar_ordenes_excel(ordenes):
    """Genera workbook Excel con las órdenes recibidas."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Ordenes de Trabajo'
    ws.append([
        'Numero Cliente',
        'Titulo',
        'Descripcion',
        'Tipo Trabajo',
        'Tecnico Responsable',
        'Estado',
        'Direccion Cliente',
        'Comuna',
        'Medidor Serie',
        'SIM IMEI',
        'Modem Serie',
        'Observaciones Tecnicas',
        'Fecha Creacion',
        'Fecha Asignacion',
        'Fecha Fin Ejecucion',
        'Creada Por',
        'ID Orden',
        'Alerta Duplicado',
        'Descripcion Alerta',
    ])

    for orden in ordenes:
        ws.append([
            orden.cliente.numero_cliente if orden.cliente else '',
            orden.titulo or '',
            orden.descripcion or '',
            orden.get_tipo_trabajo_display(),
            orden.tecnico_responsable.nombre_interno if orden.tecnico_responsable else '',
            orden.get_estado_display(),
            orden.cliente.direccion if orden.cliente else '',
            orden.cliente.comuna if orden.cliente else '',
            orden.medidor.serie if orden.medidor else '',
            orden.simcard.imei if orden.simcard else '',
            orden.modem.serie if orden.modem else '',
            orden.observaciones_tecnicas or '',
            orden.fecha_creacion.strftime('%d/%m/%Y %H:%M') if orden.fecha_creacion else '',
            orden.fecha_asignacion.strftime('%d/%m/%Y %H:%M') if orden.fecha_asignacion else '',
            orden.fecha_fin_ejecucion.strftime('%d/%m/%Y %H:%M') if orden.fecha_fin_ejecucion else '',
            orden.creada_por.nombre_interno if orden.creada_por else '',
            orden.id,
            'SI' if orden.alerta_duplicado else 'NO',
            orden.descripcion_alerta_duplicado or '',
        ])

    return wb


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
