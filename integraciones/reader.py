"""
Lector de registros MoreApp desde carpetas locales.

MoreApp deposita los archivos via FTPS en una estructura como:
    Registros/{customerId}/{formName}/{correlativo}/registration.json

Este módulo recorre esa estructura, detecta carpetas nuevas no procesadas,
lee el registration.json y lo registra en la base de datos con deduplicación
y detección de alertas de doble trabajo.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Ruta base donde MoreApp deposita los registros (configurable desde settings)
DEFAULT_REGISTROS_BASE = os.path.join(
    str(Path(__file__).resolve().parent.parent),
    'Registros',
)

# Campos mínimos obligatorios que debe tener el JSON para ser válido
CAMPOS_MINIMOS = ('id', 'info', 'meta', 'data')



def _extraer_datos_normalizados(data: dict) -> Dict[str, Any]:
    """
    Extrae los campos operativos clave de un registration.json
    para consulta rápida en Reportes sin tener que parsear el JSON completo.
    """
    info = data.get('info', {})
    meta = data.get('meta', {})
    campos = data.get('data', {})
    buscar_cliente = campos.get('buscarCliente', {})

    return {
        'form_name': info.get('formName', ''),
        'fecha_registro': meta.get('registrationDate', ''),
        'serial_number': meta.get('serialNumber'),
        'empresa': campos.get('empresa', ''),
        'actividad': campos.get('actividad', ''),
        'estado': campos.get('estado', ''),
        'cliente_codigo': campos.get('cliente', ''),
        'cliente_nombre': buscar_cliente.get('NOMBRE', ''),
        'cliente_direccion': buscar_cliente.get('DIRECCION', ''),
        'cliente_comuna': buscar_cliente.get('COMUNA', ''),
        'trabajo': buscar_cliente.get('TRABAJO', ''),
        'con_sim': campos.get('conOSinChip', ''),
        'tipo_telemetria': campos.get('tipoDeTelemetria', ''),
        'tecnico_responsable': (
            campos.get('tECNICORESPONSABLE', {}).get('NOMBRES', '')
            or campos.get('tcnicoResponsableCertelec', {}).get('nombres', '')
        ),
        'tecnico_asistente': campos.get('tcnicoAsistente', {}).get('NOMBRES', ''),
        'observacion': campos.get('observacinDelTrabajo', ''),
        'fecha_trabajo': campos.get('fecha', ''),
        'location': campos.get('location', {}).get('formattedValue', ''),
    }


def _detectar_alerta_doble_trabajo(submission_id: str, datos: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Detecta si existe un registro previo para el mismo cliente + trabajo en una
    ventana de tiempo corta (mismo día = alta, 7 días = media).

    Returns:
        (tiene_alerta: bool, descripcion: str)
    """
    from ordenes_trabajo.models import IntegracionMoreApp

    cliente = datos.get('cliente_codigo', '').strip()
    trabajo = datos.get('trabajo', '').strip() or datos.get('actividad', '').strip()

    if not cliente or not trabajo:
        return False, ''

    ahora = timezone.now()
    ventana_alta = ahora - timedelta(days=1)
    ventana_media = ahora - timedelta(days=7)

    # Excluir el propio registro (puede que ya exista como DUPLICADO)
    candidatos = IntegracionMoreApp.objects.exclude(
        moreapp_submission_id=submission_id
    ).filter(
        fecha_recepcion__gte=ventana_media,
    ).exclude(
        estado_sincronizacion='DUPLICADO'
    )

    for candidato in candidatos:
        datos_c = candidato.datos_procesados
        if not datos_c:
            continue
        cliente_c = datos_c.get('cliente_codigo', '').strip()
        trabajo_c = (datos_c.get('trabajo', '').strip()
                     or datos_c.get('actividad', '').strip())

        if cliente_c == cliente and trabajo_c == trabajo:
            if candidato.fecha_recepcion >= ventana_alta:
                severidad = 'Alta (mismo día)'
            else:
                severidad = 'Media (últimos 7 días)'

            desc = (
                f'Posible doble trabajo — Cliente: {cliente} | '
                f'Actividad: {trabajo} | Severidad: {severidad} | '
                f'Registro anterior: #{candidato.numero_correlativo} '
                f'({candidato.fecha_recepcion.strftime("%d/%m/%Y %H:%M")})'
            )
            return True, desc

    return False, ''


def leer_carpetas(base_dir: str = None, dry_run: bool = False) -> Dict[str, Any]:
    """
    Recorre la estructura de carpetas de MoreApp y registra los submissions nuevos.

    Estructura esperada:
        {base_dir}/{customerId}/{formName}/{correlativo}/registration.json

    Args:
        base_dir: Ruta raíz donde están los registros. Si es None usa DEFAULT o settings.
        dry_run:  Si True, detecta carpetas pero no guarda en BD.

    Returns:
        Dict con estadísticas: nuevos, duplicados, errores, alertas, omitidos.
    """
    from ordenes_trabajo.models import IntegracionMoreApp

    base = base_dir or getattr(settings, 'MOREAPP_REGISTROS_DIR', DEFAULT_REGISTROS_BASE)

    stats = {
        'base_dir': base,
        'nuevos': 0,
        'duplicados': 0,
        'alertas': 0,
        'errores': 0,
        'omitidos': 0,
        'detalle': [],
    }

    if not os.path.isdir(base):
        logger.warning('Directorio base no encontrado: %s', base)
        stats['detalle'].append({'error': f'Directorio no encontrado: {base}'})
        return stats

    # Recorrer: base / customerId / formName / correlativo /
    for customer_id in os.listdir(base):
        customer_path = os.path.join(base, customer_id)
        if not os.path.isdir(customer_path):
            continue

        for form_name in os.listdir(customer_path):
            form_path = os.path.join(customer_path, form_name)
            if not os.path.isdir(form_path):
                continue

            for correlativo in sorted(os.listdir(form_path), key=lambda x: int(x) if x.isdigit() else 0):
                correlativo_path = os.path.join(form_path, correlativo)
                json_path = os.path.join(correlativo_path, 'registration.json')

                if not os.path.isfile(json_path):
                    stats['omitidos'] += 1
                    continue

                resultado = _procesar_json(
                    json_path=json_path,
                    ruta_carpeta=correlativo_path,
                    numero_correlativo=int(correlativo) if correlativo.isdigit() else None,
                    dry_run=dry_run,
                )
                stats['detalle'].append(resultado)

                if resultado['resultado'] == 'nuevo':
                    stats['nuevos'] += 1
                    if resultado.get('alerta'):
                        stats['alertas'] += 1
                elif resultado['resultado'] == 'duplicado':
                    stats['duplicados'] += 1
                elif resultado['resultado'] == 'error':
                    stats['errores'] += 1

    logger.info(
        'Lectura completada — nuevos=%d duplicados=%d alertas=%d errores=%d',
        stats['nuevos'], stats['duplicados'], stats['alertas'], stats['errores'],
    )
    return stats


def _procesar_json(json_path: str, ruta_carpeta: str,
                   numero_correlativo: int, dry_run: bool) -> Dict[str, Any]:
    """Procesa un registration.json individual y lo registra en BD."""
    from ordenes_trabajo.models import IntegracionMoreApp

    resultado = {
        'json_path': json_path,
        'ruta_carpeta': ruta_carpeta,
        'correlativo': numero_correlativo,
        'resultado': 'error',
        'submission_id': None,
        'alerta': False,
        'mensaje': '',
    }

    # --- Leer archivo ---
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        resultado['mensaje'] = f'JSON inválido: {exc}'
        resultado['resultado'] = 'error'
        if not dry_run:
            _guardar_error(json_path, ruta_carpeta, numero_correlativo,
                           'ERROR_JSON', str(exc), {})
        logger.warning('JSON inválido en %s: %s', json_path, exc)
        return resultado
    except OSError as exc:
        resultado['mensaje'] = f'Error de lectura: {exc}'
        resultado['resultado'] = 'error'
        logger.warning('Error leyendo %s: %s', json_path, exc)
        return resultado

    # --- Validación mínima ---
    for campo in CAMPOS_MINIMOS:
        if campo not in data:
            resultado['mensaje'] = f'Campo mínimo faltante: {campo}'
            resultado['resultado'] = 'error'
            if not dry_run:
                _guardar_error(json_path, ruta_carpeta, numero_correlativo,
                               'ERROR_JSON', resultado['mensaje'], data)
            return resultado

    submission_id = data.get('id', '')
    resultado['submission_id'] = submission_id
    nombre_formulario = data.get('info', {}).get('formName', '')

    if dry_run:
        existe = IntegracionMoreApp.objects.filter(
            moreapp_submission_id=submission_id
        ).exists()
        resultado['resultado'] = 'duplicado' if existe else 'nuevo'
        resultado['mensaje'] = 'dry-run'
        return resultado

    # --- Deduplicación por id ---
    if IntegracionMoreApp.objects.filter(moreapp_submission_id=submission_id).exists():
        resultado['resultado'] = 'duplicado'
        resultado['mensaje'] = f'Ya existe registro con id={submission_id}'
        logger.info('Duplicado omitido: %s', submission_id)
        return resultado

    # --- Extraer datos normalizados ---
    datos_norm = _extraer_datos_normalizados(data)

    # --- Detección alerta doble trabajo ---
    tiene_alerta, desc_alerta = _detectar_alerta_doble_trabajo(submission_id, datos_norm)

    # --- Guardar en BD ---
    with transaction.atomic():
        estado = 'ALERTA_REVISION' if tiene_alerta else 'PROCESADO'
        IntegracionMoreApp.objects.create(
            moreapp_submission_id=submission_id,
            nombre_formulario=nombre_formulario,
            numero_correlativo=numero_correlativo,
            ruta_carpeta=ruta_carpeta,
            datos_recibidos=data,
            datos_procesados=datos_norm,
            estado_sincronizacion=estado,
            alerta_doble_trabajo=tiene_alerta,
            descripcion_alerta=desc_alerta,
            fecha_procesamiento=timezone.now(),
        )

    resultado['resultado'] = 'nuevo'
    resultado['alerta'] = tiene_alerta
    resultado['mensaje'] = desc_alerta if tiene_alerta else 'OK'
    logger.info('Registrado: %s (alerta=%s)', submission_id, tiene_alerta)
    return resultado


def _guardar_error(json_path, ruta_carpeta, numero_correlativo, estado, mensaje, data):
    """Registra en BD un submission que no pudo procesarse correctamente."""
    from ordenes_trabajo.models import IntegracionMoreApp

    submission_id = data.get('id', '') if data else ''
    if not submission_id:
        submission_id = f'error_{os.path.basename(ruta_carpeta)}_{datetime.now().timestamp()}'

    if IntegracionMoreApp.objects.filter(moreapp_submission_id=submission_id).exists():
        return

    IntegracionMoreApp.objects.create(
        moreapp_submission_id=submission_id,
        nombre_formulario=data.get('info', {}).get('formName', '') if data else '',
        numero_correlativo=numero_correlativo,
        ruta_carpeta=ruta_carpeta,
        datos_recibidos=data or {},
        estado_sincronizacion=estado,
        mensaje_error=mensaje,
        fecha_procesamiento=timezone.now(),
    )
