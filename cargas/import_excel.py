"""Importación masiva de cargas / órdenes de trabajo administrativas desde Excel."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from django.db import transaction

from clientes.models import Cliente
from importaciones.models import ImportacionExcel, ImportacionExcelError
from ordenes_trabajo.models import OrdenTrabajo
from usuarios.models import Usuario

from .models import CargaAdministrativa
from .services import crear_carga

COLUMNAS = {
    'titulo': {'titulo', 'título', 'title'},
    'tipo': {'tipo', 'tipo carga', 'tipo_carga'},
    'prioridad': {'prioridad'},
    'descripcion': {'descripcion', 'descripción', 'detalle'},
    'asignado': {
        'asignado', 'asignado a', 'asignado_a', 'responsable',
        'email', 'usuario', 'rut asignado',
    },
    'cliente': {
        'cliente', 'numero cliente', 'número cliente', 'nro cliente',
        'num cliente', 'id cliente',
    },
    'orden': {'orden', 'id orden', 'ot', 'orden trabajo', 'id ot'},
    'url': {'url', 'url referencia', 'referencia', 'enlace'},
    'id_carga': {'id carga', 'id', 'id carga administrativa'},
}

TIPOS_ALIAS = {
    'validacion ot': 'VALIDACION_OT',
    'validación ot': 'VALIDACION_OT',
    'validacion de ot': 'VALIDACION_OT',
    'validación de ot': 'VALIDACION_OT',
    'validacion_ot': 'VALIDACION_OT',
    'sci4': 'VERIFICACION_SCI4',
    'verificacion sci4': 'VERIFICACION_SCI4',
    'verificación sci4': 'VERIFICACION_SCI4',
    'actualizacion base comercial': 'VERIFICACION_SCI4',
    'actualización base comercial (sci4)': 'VERIFICACION_SCI4',
    'verificacion_sci4': 'VERIFICACION_SCI4',
    'moreapp': 'REVISION_MOREAPP',
    'revision moreapp': 'REVISION_MOREAPP',
    'revisión moreapp': 'REVISION_MOREAPP',
    'revision_moreapp': 'REVISION_MOREAPP',
    'comunicacion': 'COMUNICACION',
    'comunicación': 'COMUNICACION',
    'validacion de comunicacion': 'COMUNICACION',
    'validación de comunicación': 'COMUNICACION',
    'verificacion': 'VERIFICACION',
    'verificación': 'VERIFICACION',
    'verificacion administrativa': 'VERIFICACION',
    'verificación administrativa': 'VERIFICACION',
    'otro': 'OTRO',
}

PRIORIDADES_ALIAS = {
    'baja': 'BAJA',
    'media': 'MEDIA',
    'alta': 'ALTA',
    'low': 'BAJA',
    'medium': 'MEDIA',
    'high': 'ALTA',
}


def _limpiar_header(valor) -> str:
    if valor is None:
        return ''
    texto = str(valor).strip().lower()
    texto = re.sub(r'\s+', ' ', texto)
    return texto


def _mapear_headers(headers: List[Any]) -> Dict[str, int]:
    indice: Dict[str, int] = {}
    for i, raw in enumerate(headers):
        clave = _limpiar_header(raw)
        if not clave:
            continue
        for campo, alias in COLUMNAS.items():
            if clave in alias and campo not in indice:
                indice[campo] = i
                break
    return indice


def _valor_fila(valores: List[Any], indice: Dict[str, int], campo: str) -> str:
    if campo not in indice:
        return ''
    i = indice[campo]
    if i >= len(valores):
        return ''
    v = valores[i]
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _fila_a_texto(headers: List[Any], valores: List[Any]) -> str:
    partes = []
    for h, v in zip(headers, valores):
        if h is None and (v is None or str(v).strip() == ''):
            continue
        partes.append(f'{h}={v}')
    return ' | '.join(partes)[:2000]


def _resolver_tipo(raw: str) -> str:
    if not raw:
        return 'VERIFICACION'
    codigo = raw.strip().upper().replace(' ', '_')
    validos = {c[0] for c in CargaAdministrativa.TIPO_CHOICES}
    if codigo in validos:
        return codigo
    alias = TIPOS_ALIAS.get(_limpiar_header(raw))
    if alias:
        return alias
    raise ValueError(
        f'Tipo no reconocido: «{raw}». '
        f'Use: {", ".join(sorted(validos))} o su etiqueta.'
    )


def _resolver_prioridad(raw: str) -> str:
    if not raw:
        return 'MEDIA'
    codigo = raw.strip().upper()
    validos = {p[0] for p in CargaAdministrativa.PRIORIDAD_CHOICES}
    if codigo in validos:
        return codigo
    alias = PRIORIDADES_ALIAS.get(_limpiar_header(raw))
    if alias:
        return alias
    raise ValueError(f'Prioridad no reconocida: «{raw}». Use BAJA, MEDIA o ALTA.')


def _resolver_asignado(raw: str) -> Optional[Usuario]:
    if not raw:
        return None
    texto = raw.strip()
    qs = Usuario.objects.filter(rol__in=['ADMIN', 'ADMINISTRATIVO'], is_active=True)
    user = (
        qs.filter(email__iexact=texto).first()
        or qs.filter(nombre_interno__iexact=texto).first()
        or qs.filter(rut__iexact=texto).first()
        or qs.filter(username__iexact=texto).first()
    )
    if not user:
        raise ValueError(
            f'Asignado «{texto}» no encontrado (debe ser ADMIN o ADMINISTRATIVO activo).'
        )
    return user


def _resolver_cliente(raw: str) -> Optional[Cliente]:
    if not raw:
        return None
    texto = raw.strip()
    cliente = Cliente.objects.filter(numero_cliente__iexact=texto, activo=True).first()
    if not cliente and texto.isdigit():
        cliente = Cliente.objects.filter(pk=int(texto), activo=True).first()
    if not cliente:
        raise ValueError(f'Cliente «{texto}» no encontrado o inactivo.')
    return cliente


def _resolver_orden(raw: str) -> Optional[OrdenTrabajo]:
    if not raw:
        return None
    texto = raw.strip()
    if not texto.isdigit():
        raise ValueError(f'ID Orden inválido: «{texto}». Debe ser numérico.')
    orden = OrdenTrabajo.objects.filter(pk=int(texto), eliminado=False).first()
    if not orden:
        raise ValueError(f'Orden de trabajo #{texto} no encontrada.')
    return orden


def _clave_duplicado(
    titulo: str,
    tipo: str,
    cliente_id: Optional[int],
    orden_id: Optional[int],
) -> Tuple[str, str, Optional[int], Optional[int]]:
    return (titulo.strip().casefold(), tipo, cliente_id, orden_id)


def _buscar_duplicado_db(
    titulo: str,
    tipo: str,
    cliente_id: Optional[int],
    orden_id: Optional[int],
) -> Optional[CargaAdministrativa]:
    qs = CargaAdministrativa.objects.filter(
        eliminado=False,
        titulo__iexact=titulo.strip(),
        tipo=tipo,
    )
    if cliente_id:
        qs = qs.filter(cliente_id=cliente_id)
    else:
        qs = qs.filter(cliente_id__isnull=True)
    if orden_id:
        qs = qs.filter(orden_id=orden_id)
    else:
        qs = qs.filter(orden_id__isnull=True)
    return qs.order_by('-fecha_creacion').first()


def importar_cargas_excel(archivo, usuario) -> ImportacionExcel:
    """
    Crea cargas administrativas desde Excel.
    No sobrescribe registros existentes: los duplicados se reportan y se omiten.
    """
    importacion = ImportacionExcel.objects.create(
        tipo='CARGAS_ADMINISTRATIVAS',
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

        if 'titulo' not in indice:
            raise ValueError(
                'El Excel debe incluir la columna «Titulo». '
                f'Columnas detectadas: {", ".join(str(h) for h in headers if h)}'
            )

        contador = 0
        exitosas = 0
        errores = 0
        duplicados = 0
        claves_archivo: set = set()

        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=False), start=2):
            valores = [cell.value for cell in row]
            if not any(v is not None and str(v).strip() != '' for v in valores):
                continue

            titulo_raw = _valor_fila(valores, indice, 'titulo')
            if titulo_raw and _limpiar_header(titulo_raw) in COLUMNAS['titulo']:
                # Fila de encabezado repetida
                continue

            contador += 1
            try:
                titulo = titulo_raw
                if not titulo:
                    raise ValueError('Titulo es obligatorio')

                tipo = _resolver_tipo(_valor_fila(valores, indice, 'tipo'))
                prioridad = _resolver_prioridad(_valor_fila(valores, indice, 'prioridad'))
                descripcion = _valor_fila(valores, indice, 'descripcion')
                asignado = _resolver_asignado(_valor_fila(valores, indice, 'asignado'))
                cliente = _resolver_cliente(_valor_fila(valores, indice, 'cliente'))
                orden = _resolver_orden(_valor_fila(valores, indice, 'orden'))
                url_referencia = _valor_fila(valores, indice, 'url')
                id_carga_raw = _valor_fila(valores, indice, 'id_carga')

                if id_carga_raw:
                    if not id_carga_raw.isdigit():
                        raise ValueError(f'ID Carga inválido: «{id_carga_raw}»')
                    existente_id = CargaAdministrativa.objects.filter(
                        pk=int(id_carga_raw),
                        eliminado=False,
                    ).first()
                    if existente_id:
                        duplicados += 1
                        ImportacionExcelError.objects.create(
                            importacion=importacion,
                            numero_fila=idx,
                            motivo=(
                                f'Duplicado: ya existe la carga administrativa #{existente_id.pk}. '
                                'La carga masiva no sobrescribe registros existentes.'
                            ),
                            data_cruda=_fila_a_texto(headers, valores),
                        )
                        continue

                clave = _clave_duplicado(
                    titulo,
                    tipo,
                    cliente.pk if cliente else None,
                    orden.pk if orden else None,
                )
                if clave in claves_archivo:
                    duplicados += 1
                    ImportacionExcelError.objects.create(
                        importacion=importacion,
                        numero_fila=idx,
                        motivo=(
                            'Duplicado en el archivo: misma combinación de '
                            'Título + Tipo + Cliente + Orden que otra fila.'
                        ),
                        data_cruda=_fila_a_texto(headers, valores),
                    )
                    continue

                existente = _buscar_duplicado_db(
                    titulo,
                    tipo,
                    cliente.pk if cliente else None,
                    orden.pk if orden else None,
                )
                if existente:
                    duplicados += 1
                    ImportacionExcelError.objects.create(
                        importacion=importacion,
                        numero_fila=idx,
                        motivo=(
                            f'Duplicado: ya existe la carga #{existente.pk} '
                            f'con el mismo título, tipo y referencias '
                            f'(estado {existente.get_estado_display()}). '
                            'No se sobrescribe.'
                        ),
                        data_cruda=_fila_a_texto(headers, valores),
                    )
                    continue

                with transaction.atomic():
                    crear_carga(
                        usuario,
                        titulo=titulo,
                        tipo=tipo,
                        descripcion=descripcion,
                        prioridad=prioridad,
                        asignado_a=asignado,
                        orden=orden,
                        cliente=cliente,
                        url_referencia=url_referencia,
                    )
                claves_archivo.add(clave)
                exitosas += 1
            except Exception as exc:
                errores += 1
                ImportacionExcelError.objects.create(
                    importacion=importacion,
                    numero_fila=idx,
                    motivo=str(exc),
                    data_cruda=_fila_a_texto(headers, valores),
                )

        importacion.total_filas = contador
        importacion.exitosas = exitosas
        importacion.fallidas = errores + duplicados
        importacion.estado = (
            'COMPLETADO' if contador > 0 and exitosas > 0
            else ('ERROR' if contador == 0 else 'COMPLETADO')
        )
        if contador == 0:
            importacion.observaciones = 'No se encontraron filas con datos para importar.'
        else:
            importacion.observaciones = (
                f'Total de registros encontrados: {contador}. '
                f'Registros cargados correctamente: {exitosas}. '
                f'Registros con errores: {errores}. '
                f'Registros duplicados: {duplicados}.'
            )
        # Metadatos extra para la respuesta JSON (parseables)
        importacion.observaciones += f'\n[meta] errores={errores};duplicados={duplicados}'
        importacion.save()
        # Adjuntar conteos en el objeto en memoria para la vista
        importacion._conteo_errores = errores  # type: ignore[attr-defined]
        importacion._conteo_duplicados = duplicados  # type: ignore[attr-defined]
    except Exception as exc:
        importacion.estado = 'ERROR'
        importacion.observaciones = f'Error en importación: {exc}'
        importacion.save()
        importacion._conteo_errores = 0  # type: ignore[attr-defined]
        importacion._conteo_duplicados = 0  # type: ignore[attr-defined]

    return importacion


def resumen_importacion(importacion: ImportacionExcel) -> Dict[str, int]:
    """Extrae conteos de errores/duplicados desde observaciones o atributos."""
    errores = getattr(importacion, '_conteo_errores', None)
    duplicados = getattr(importacion, '_conteo_duplicados', None)
    if errores is not None and duplicados is not None:
        return {'errores': int(errores), 'duplicados': int(duplicados)}

    obs = importacion.observaciones or ''
    m_err = re.search(r'Registros con errores:\s*(\d+)', obs)
    m_dup = re.search(r'Registros duplicados:\s*(\d+)', obs)
    if m_err and m_dup:
        return {'errores': int(m_err.group(1)), 'duplicados': int(m_dup.group(1))}

    # Fallback: clasificar errores guardados
    dups = 0
    errs = 0
    for e in importacion.errores.all():
        if (e.motivo or '').startswith('Duplicado'):
            dups += 1
        else:
            errs += 1
    return {'errores': errs, 'duplicados': dups}


def exportar_cargas_excel(cargas):
    """Genera workbook Excel con las cargas administrativas recibidas."""
    from importaciones.utils import aplicar_estilo_hoja_exportacion

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Cargas administrativas'
    ws.append([
        'ID Carga',
        'Titulo',
        'Tipo',
        'Prioridad',
        'Estado',
        'Descripcion',
        'Asignado',
        'Cliente',
        'ID Orden',
        'URL',
        'Observaciones',
        'Creado por',
        'Fecha creacion',
        'Fecha asignacion',
        'Fecha completada',
    ])

    for carga in cargas:
        ws.append([
            carga.id,
            carga.titulo or '',
            carga.get_tipo_display(),
            carga.get_prioridad_display(),
            carga.get_estado_display(),
            carga.descripcion or '',
            carga.asignado_a.nombre_interno if carga.asignado_a_id else '',
            carga.cliente.numero_cliente if carga.cliente_id else '',
            carga.orden_id or '',
            carga.url_referencia or '',
            carga.observaciones or '',
            carga.creado_por.nombre_interno if carga.creado_por_id else '',
            carga.fecha_creacion.strftime('%d/%m/%Y %H:%M') if carga.fecha_creacion else '',
            carga.fecha_asignacion.strftime('%d/%m/%Y %H:%M') if carga.fecha_asignacion else '',
            carga.fecha_completada.strftime('%d/%m/%Y %H:%M') if carga.fecha_completada else '',
        ])

    # Filtro en Tipo / Prioridad / Estado / Asignado / Cliente (cols 3–8).
    aplicar_estilo_hoja_exportacion(ws, auto_filter=True, filter_from_col=3, filter_to_col=8)
    return wb
