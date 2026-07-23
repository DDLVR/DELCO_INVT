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
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import unicodedata

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Revisiones ya cerradas manualmente: el sync no debe reabrirlas
ESTADOS_REVISION_CERRADOS = frozenset({'REVISADO', 'DESCARTADO'})


def _asignar_estado_revision(registro, nuevo_estado: str) -> None:
    """Actualiza estado_revision respetando REVISADO/DESCARTADO manuales."""
    actual = (getattr(registro, 'estado_revision', None) or '').strip().upper()
    if actual in ESTADOS_REVISION_CERRADOS:
        return
    registro.estado_revision = nuevo_estado


def _append_descripcion_alerta(registro, detalle: str) -> None:
    """Agrega un tramo a descripcion_alerta sin duplicar el mismo texto."""
    nuevo = str(detalle or '').strip()
    if not nuevo:
        return
    actual = str(getattr(registro, 'descripcion_alerta', None) or '').strip()
    if not actual:
        registro.descripcion_alerta = nuevo
        return
    if nuevo in actual:
        return
    # Evitar concatenar el mismo bloque operativo dos veces (reproceso / doble llamada)
    registro.descripcion_alerta = f'{actual} | {nuevo}'


def _finalizar_datos_procesados(
    datos_norm: Dict[str, Any],
    payload: Dict[str, Any],
    registro=None,
    resumen_operativo: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Une datos normalizados + resultado operativo + GPS/fotos MoreApp."""
    from integraciones.moreapp_media import enriquecer_datos_media, crear_adjuntos_orden_desde_fotos

    ruta = ''
    submission_id = ''
    if registro is not None:
        ruta = getattr(registro, 'ruta_carpeta', '') or ''
        submission_id = getattr(registro, 'moreapp_submission_id', '') or ''
    enriquecidos = enriquecer_datos_media(
        datos_norm or {},
        payload or {},
        ruta_carpeta=ruta,
        submission_id=submission_id,
    )
    if resumen_operativo is not None:
        enriquecidos = {**enriquecidos, 'resultado_operativo': resumen_operativo}

    if registro is not None and getattr(registro, 'orden_id', None):
        try:
            crear_adjuntos_orden_desde_fotos(registro.orden, registro)
        except Exception:
            logger.exception(
                'No se pudieron crear adjuntos fotográficos para MoreApp %s',
                submission_id,
            )
    return enriquecidos


# Ruta base donde MoreApp deposita los registros (configurable desde settings)
DEFAULT_REGISTROS_BASE = os.path.join(
    str(Path(__file__).resolve().parent.parent),
    'Registros',
)

# Campos mínimos obligatorios que debe tener el JSON para ser válido
CAMPOS_MINIMOS = ('id', 'info', 'meta', 'data')

FORMULARIOS_SOPORTADOS = {
    'lectura': 'LECTURA',
    'mantenimiento telemetria v3': 'MANTENIMIENTO_TELEMETRIA_V3',
    'registro de medidores y telemetria v3': 'REGISTRO_MEDIDORES_TELEMETRIA_V3',
}

SYNC_STATE_FILENAME = '.moreapp_sync_state.json'


def _cargar_estado_sync(base_dir: str) -> Dict[str, Any]:
    """Carga el estado incremental desde disco; si no existe, retorna estructura vacía."""
    path = os.path.join(base_dir, SYNC_STATE_FILENAME)
    if not os.path.isfile(path):
        return {'version': 1, 'forms': {}}

    try:
        with open(path, 'r', encoding='utf-8-sig') as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {'version': 1, 'forms': {}}
        forms = data.get('forms')
        if not isinstance(forms, dict):
            forms = {}
        return {'version': 1, 'forms': forms}
    except Exception:
        logger.exception('No se pudo leer estado incremental MoreApp; se usará escaneo completo')
        return {'version': 1, 'forms': {}}


def _guardar_estado_sync(base_dir: str, estado: Dict[str, Any]) -> None:
    """Guarda el estado incremental de forma atómica."""
    path = os.path.join(base_dir, SYNC_STATE_FILENAME)
    tmp_path = f'{path}.tmp'
    payload = {'version': 1, 'forms': estado.get('forms', {})}
    with open(tmp_path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=True, indent=2)
    os.replace(tmp_path, path)


def _clave_estado_form(customer_id: str, form_name: str) -> str:
    return f'{customer_id}/{form_name}'


def _normalizar_texto(texto: Any) -> str:
    valor = str(texto or '').strip().lower().replace('_', ' ').replace('-', ' ')
    valor = unicodedata.normalize('NFKD', valor)
    valor = ''.join(c for c in valor if not unicodedata.combining(c))
    return ' '.join(valor.split())


IDENTIFICADORES_DESCARTADOS = {
    '',
    '-',
    '--',
    'n a',
    'na',
    'n/d',
    'nd',
    'id',
    'sin modem',
    'sin modem ',
    'sin modems',
    'sin medidor',
    'sin sim',
    'robado',
    'retirado',
    'en base',
    'no habia modem',
    'no hay modem',
    'prueba fco',
    'teltonika',
}


def _limpiar_identificador_operativo(valor: Any, modo: str = 'general') -> str:
    identificador = _as_text(valor)
    if not identificador:
        return ''

    identificador = identificador.replace(',', ' ').strip()
    if modo == 'ip':
        identificador = re.sub(r'\s+', '', identificador)
    else:
        identificador = re.sub(r'\s+', ' ', identificador)
    return identificador.strip()


def _identificador_operativo_util(valor: Any, modo: str = 'general') -> str:
    identificador = _limpiar_identificador_operativo(valor, modo=modo)
    if not identificador:
        return ''

    normalizado = _normalizar_texto(identificador)
    if normalizado in IDENTIFICADORES_DESCARTADOS or normalizado.startswith('sin '):
        return ''

    if modo == 'ip':
        if not re.fullmatch(r'[0-9.]+', identificador):
            return ''
        if identificador.count('.') < 3:
            return ''
    elif not any(ch.isdigit() for ch in identificador):
        return ''

    return identificador


def _as_text(valor: Any) -> str:
    """Convierte a texto seguro para MySQL en Hostingplus.

    MoreApp a veces envía � (U+FFFD) u el mojibake latin1 de esos bytes
    (EF BF BD). Sin filtrar, PyMySQL lanza DataError 1366.
    """
    if valor is None:
        return ''
    if isinstance(valor, bytes):
        texto = valor.decode('utf-8', errors='replace')
    else:
        texto = str(valor)

    # Null, BOM, replacement char y su mojibake típico (EF BF BD como 3 chars)
    texto = (
        texto.replace('\x00', '')
        .replace('\ufeff', '')
        .replace('\ufffd', '')
        .replace('\u00ef\u00bf\u00bd', '')
        .replace(chr(0xEF) + chr(0xBF) + chr(0xBD), '')
    )
    texto = ''.join(
        ch for ch in texto
        if ch in '\t\n\r' or unicodedata.category(ch)[0] != 'C'
    )
    texto = ' '.join(texto.split())

    # Columnas de clientes en producción pueden ser latin1 (1 byte).
    seguro = []
    for ch in texto:
        o = ord(ch)
        if o < 128:
            seguro.append(ch)
            continue
        if o < 256:
            # latin1 imprimible; evita secuencias problemáticas al reinterpretarse
            seguro.append(ch)
            continue
        for part in unicodedata.normalize('NFKD', ch):
            po = ord(part)
            if po < 256 and not unicodedata.combining(part):
                seguro.append(part)
    limpio = ''.join(seguro).strip()
    # Segunda pasada: quitar trío EF BF BD si reapareció
    while True:
        idx = limpio.find(chr(0xEF) + chr(0xBF) + chr(0xBD))
        if idx < 0:
            break
        limpio = limpio[:idx] + limpio[idx + 3:]
    return limpio.strip()


def _sanitizar_cliente_para_mysql(cliente_obj) -> None:
    """Limpia Char/Text del cliente in-place antes de save (defensa extra)."""
    campos_texto = (
        'numero_cliente', 'direccion', 'comuna', 'referencia', 'tipo_suministro',
        'pod', 'sector', 'city', 'customer_name', 'installation_address',
        'proyecto', 'meter_manufacturer_id', 'meter_serial_n_1', 'empresa',
        'ip', 'puerto', 'modem', 'estado_telemetria', 'note', 'trabajo',
        'sim_operador', 'sim_iccid', 'sim_abonado',
        'estado_restriccion', 'justificacion_restriccion',
    )
    for campo in campos_texto:
        if not hasattr(cliente_obj, campo):
            continue
        actual = getattr(cliente_obj, campo, None)
        if actual is None or actual == '':
            continue
        limpio = _as_text(actual)
        if limpio != actual:
            setattr(cliente_obj, campo, limpio)


def _as_text_mysql_strict(valor: Any) -> str:
    """Texto para columnas de dirección/comuna: ASCII tras quitar acentos (máxima compatibilidad Hostingplus)."""
    texto = _as_text(valor)
    if not texto:
        return ''
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(
        ch for ch in texto
        if not unicodedata.combining(ch) and ord(ch) < 128
    )
    return ' '.join(texto.split())


def _valor_campo_fuentes(fuentes, aliases):
    aliases_norm = {_normalizar_texto(a) for a in aliases}
    for fuente in fuentes:
        if not isinstance(fuente, dict):
            continue
        for key, val in fuente.items():
            if _normalizar_texto(key) in aliases_norm and val not in (None, '', []):
                if isinstance(val, dict):
                    for nested_key in ('NOMBRES', 'nombres', 'NOMBRE', 'nombre', 'value'):
                        nested_val = val.get(nested_key)
                        if nested_val not in (None, '', []):
                            return nested_val
                return val
    return ''


def _resolver_formulario(nombre_formulario: str) -> str:
    nombre_norm = _normalizar_texto(nombre_formulario)
    for nombre_base, canonico in FORMULARIOS_SOPORTADOS.items():
        if nombre_base in nombre_norm:
            return canonico
    return 'OTRO'


def _resolver_estado_inventario(nombre_estado: str):
    from inventario.models import EstadoInventario

    estado = _normalizar_texto(nombre_estado)
    if not estado:
        return None

    candidatos = []
    if 'instal' in estado:
        candidatos = ['Instalado']
    elif 'retir' in estado or 'baja' in estado:
        candidatos = ['Retirado', 'Dado de baja']
    elif 'repar' in estado:
        candidatos = ['En reparación']
    elif 'bodega' in estado:
        candidatos = ['En bodega']
    elif 'peaje' in estado:
        candidatos = ['En peaje']

    for cand in candidatos:
        obj = EstadoInventario.objects.filter(nombre__iexact=cand).first()
        if obj:
            return obj

    return EstadoInventario.objects.filter(nombre__icontains=estado[:20]).first()


def _obtener_estado_por_nombre(nombre_estado: str):
    from inventario.models import EstadoInventario

    if not nombre_estado:
        return None

    obj = EstadoInventario.objects.filter(nombre__iexact=nombre_estado).first()
    if obj:
        return obj

    norm = _normalizar_texto(nombre_estado)
    alias_map = {
        'instalado': ('Instalado', 'Entregado'),
        'entregado': ('Instalado',),
        'bodega': ('En bodega', 'BODEGA', 'Disponible'),
        'retirado': ('Retirado',),
        'baja': ('Dado de baja',),
        'reparacion': ('En reparación',),
        'reparacion en curso': ('En reparación',),
        'peaje': ('En peaje',),
        'trayecto': ('En Trayecto',),
        'custodia': ('En custodia técnico',),
        'revision': ('En revisión',),
    }
    for clave, candidatos in alias_map.items():
        if clave in norm:
            for candidato in candidatos:
                obj = EstadoInventario.objects.filter(nombre__iexact=candidato).first()
                if obj:
                    return obj

    return _resolver_estado_inventario(nombre_estado)


def _resolver_estado_desde_contexto(*textos):
    texto = ' '.join(_as_text(valor) for valor in textos if _as_text(valor))
    texto_norm = _normalizar_texto(texto)
    if not texto_norm:
        return None

    if any(token in texto_norm for token in ('retiro', 'retirar', 'retirado', 'desinstal', 'baja')):
        return _obtener_estado_por_nombre('Retirado') or _obtener_estado_por_nombre('Dado de baja')
    if any(token in texto_norm for token in ('instal', 'instalacion', 'cambio', 'dejado', 'montaje')):
        return _obtener_estado_por_nombre('Instalado')
    if any(token in texto_norm for token in ('repar', 'mantencion', 'mantenimiento', 'servicio tecnico')):
        return _obtener_estado_por_nombre('En reparación')
    if 'peaje' in texto_norm:
        return _obtener_estado_por_nombre('En peaje')
    if 'bodega' in texto_norm:
        return _obtener_estado_por_nombre('En bodega')
    return _resolver_estado_inventario(texto)


def _obtener_responsable_sistema():
    from usuarios.models import Usuario

    return (
        Usuario.objects.filter(rol='ADMINISTRATIVO', is_active=True).first()
        or Usuario.objects.filter(rol='ADMIN', is_active=True).first()
        or Usuario.objects.filter(is_active=True).first()
    )


def _resolver_responsable_moreapp(nombre_tecnico: str):
    """Intenta resolver el usuario técnico a partir del nombre recibido desde MoreApp."""
    from usuarios.models import Usuario

    nombre = _as_text(nombre_tecnico)
    if not nombre:
        return None

    qs_tecnicos = Usuario.objects.filter(rol='TECNICO', is_active=True)

    # Coincidencia directa por nombre interno.
    exacto = qs_tecnicos.filter(nombre_interno__iexact=nombre).first()
    if exacto:
        return exacto

    # Coincidencia parcial por nombre interno.
    parcial_interno = qs_tecnicos.filter(nombre_interno__icontains=nombre).first()
    if parcial_interno:
        return parcial_interno

    tokens = [t for t in nombre.lower().split() if len(t) >= 3]
    if tokens:
        for token in tokens:
            candidato = qs_tecnicos.filter(nombre__icontains=token).first()
            if candidato:
                return candidato
            candidato = qs_tecnicos.filter(apellido__icontains=token).first()
            if candidato:
                return candidato

    return None


def _obtener_o_crear_ubicacion(tipo: str, nombre: str):
    from inventario.models import Ubicacion

    ubicacion = Ubicacion.objects.filter(nombre__iexact=nombre).first()
    if ubicacion:
        return ubicacion

    return Ubicacion.objects.create(tipo=tipo, nombre=nombre)


def _mapear_tipo_movimiento(estado_nombre: str) -> str:
    estado = _normalizar_texto(estado_nombre)
    if 'instal' in estado:
        return 'INSTALACION'
    if 'retir' in estado or 'baja' in estado:
        return 'RETIRO'
    if 'repar' in estado:
        return 'DEVOLUCION'
    if 'bodega' in estado:
        return 'RECEPCION'
    return 'ENTREGA'


def _registrar_movimiento_equipo(
    equipo, tipo_equipo: str, observacion: str, estado_nombre: str,
    origen_sistema: str = 'MANUAL', tipo_override: str = '',
    responsable_override=None, referencia_ot: str = '',
    ubicacion_origen=None,
):
    """Registra movimiento con origen = ubicación ANTES del cambio.

    Importante: pasar ubicacion_origen si ya se mutó equipo.ubicacion_actual;
    si no, se usa la ubicación actual del equipo como origen.
    """
    from inventario.models import MovimientoInventario, MovimientoItem

    responsable = responsable_override or _obtener_responsable_sistema()
    if not responsable:
        return

    origen = (
        ubicacion_origen
        or getattr(equipo, 'ubicacion_actual', None)
        or _obtener_o_crear_ubicacion('BODEGA_DELCO', 'Bodega Principal')
    )

    estado_norm = _normalizar_texto(estado_nombre)
    if 'instal' in estado_norm:
        destino = _obtener_o_crear_ubicacion('CLIENTE', 'Instalado en cliente')
    elif 'retir' in estado_norm or 'baja' in estado_norm:
        destino = _obtener_o_crear_ubicacion('BODEGA_DELCO', 'Bodega Principal')
    elif 'repar' in estado_norm:
        destino = _obtener_o_crear_ubicacion('PROVEEDOR', 'Proveedor/Reparación')
    else:
        destino = _obtener_o_crear_ubicacion('BODEGA_DELCO', 'Bodega Principal')

    tipo_mov = tipo_override if tipo_override else _mapear_tipo_movimiento(estado_nombre)

    movimiento = MovimientoInventario.objects.create(
        tipo=tipo_mov,
        origen_sistema=origen_sistema,
        origen=origen,
        destino=destino,
        responsable=responsable,
        observacion=observacion,
        referencia_ot=referencia_ot or '',
    )

    # Actualizar ubicacion_actual del equipo al destino (Punto 4)
    if hasattr(equipo, 'ubicacion_actual'):
        if getattr(equipo, 'ubicacion_actual_id', None) != destino.id:
            equipo.ubicacion_actual = destino
            equipo.save(update_fields=['ubicacion_actual'])

    kwargs_item = {
        'movimiento': movimiento,
        'tipo_equipo': tipo_equipo,
        'cantidad': 1,
    }
    if tipo_equipo == 'MEDIDOR':
        kwargs_item['medidor'] = equipo
    elif tipo_equipo == 'MODEM':
        kwargs_item['modem'] = equipo
    elif tipo_equipo == 'SIM':
        kwargs_item['simcard'] = equipo
    MovimientoItem.objects.create(**kwargs_item)
    return movimiento


def _validar_conflicto_instalacion(equipo, tipo_equipo: str, cliente_obj) -> Optional[str]:
    """Punto 1: verifica si el equipo ya está instalado en un cliente diferente."""
    if not cliente_obj:
        return None
    from inventario.models import EstadoInventario
    estado_actual = getattr(equipo, 'estado_inventario', None)
    if not estado_actual:
        return None
    if 'instal' not in _normalizar_texto(estado_actual.nombre):
        return None
    cliente_actual_id = getattr(equipo, 'cliente_id', None)
    if cliente_actual_id and cliente_actual_id != cliente_obj.id:
        return (
            f'{tipo_equipo} {getattr(equipo, "serie", equipo.pk)} '
            f'ya instalado en cliente #{cliente_actual_id}, '
            f'se intentó actualizar a #{cliente_obj.id}'
        )
    return None


def _es_estado_instalado(estado_obj) -> bool:
    if not estado_obj:
        return False
    return 'instal' in _normalizar_texto(getattr(estado_obj, 'nombre', ''))


def _identificador_equipo(equipo, tipo_equipo: str) -> str:
    if tipo_equipo == 'MEDIDOR':
        return _as_text(getattr(equipo, 'serie', '')) or _as_text(getattr(equipo, 'pk', ''))
    if tipo_equipo == 'MODEM':
        return (
            _as_text(getattr(equipo, 'serie', ''))
            or _as_text(getattr(equipo, 'imei', ''))
            or _as_text(getattr(equipo, 'pk', ''))
        )
    return (
        _as_text(getattr(equipo, 'direccion_ip', ''))
        or _as_text(getattr(equipo, 'ip_fija', ''))
        or _as_text(getattr(equipo, 'imei', ''))
        or _as_text(getattr(equipo, 'abonado', ''))
        or _as_text(getattr(equipo, 'pk', ''))
    )


def _tiene_custodio_previo(equipo, tipo_equipo: str) -> bool:
    if tipo_equipo == 'SIM':
        return bool(getattr(equipo, 'en_custodia_de_id', None))
    if tipo_equipo == 'MODEM':
        return bool(getattr(equipo, 'en_custodia_de_id', None) or getattr(equipo, 'entregado_a_id', None))
    return bool(getattr(equipo, 'en_custodia_de_id', None) or getattr(equipo, 'entregado_a_id', None))


def _ubicacion_valida_preinstalacion(equipo) -> bool:
    ubicacion = getattr(equipo, 'ubicacion_actual', None)
    if not ubicacion:
        return False
    return ubicacion.tipo in {'BODEGA_DELCO', 'BODEGA_CONTRATISTA', 'TECNICO', 'CLIENTE'}


def _equipo_puede_instalar_desde_moreapp(equipo, tipo_equipo: str, estado_obj, cliente_obj) -> bool:
    """
    Valida si un equipo puede pasar a Instalado desde MoreApp.
    Acepta equipos en bodega/trayecto/custodia aunque no tengan FK de custodio
    o ubicación cargada (común en importaciones Excel).
    """
    if not _es_estado_instalado(estado_obj):
        return True

    if _tiene_custodio_previo(equipo, tipo_equipo):
        return True
    if _ubicacion_valida_preinstalacion(equipo):
        return True

    estado_actual = getattr(equipo, 'estado_inventario', None)
    if not estado_actual:
        return True

    if _es_estado_instalado(estado_actual):
        if cliente_obj and getattr(equipo, 'cliente_id', None) == cliente_obj.id:
            return True
        return False

    nombre = _normalizar_texto(estado_actual.nombre)
    tokens_preinstalacion = (
        'bodega', 'trayecto', 'custodia', 'retir', 'repar', 'revision',
        'peaje', 'disponible', 'transito',
    )
    if any(token in nombre for token in tokens_preinstalacion):
        return True

    return not _es_estado_instalado(estado_actual)


def _registrar_alerta_critica_asignacion(
    registro,
    tipo_equipo: str,
    identificador: str,
    motivo: str,
    contexto: str = '',
    registrar_pendiente=None,
):
    """Alerta crítica: no se auto-corrige; queda pendiente de revisión manual."""
    detalle = f'ALERTA_CRITICA | {tipo_equipo} {identificador}: {motivo}'
    if contexto:
        detalle += f' | CONTEXTO: {contexto}'
    logger.error('[MoreApp] %s', detalle)
    # Flag histórico de “alerta”; la UI distingue crítica vs doble trabajo por el texto.
    registro.alerta_doble_trabajo = True
    _asignar_estado_revision(registro, 'CON_ADVERTENCIA')
    _append_descripcion_alerta(registro, detalle)
    if callable(registrar_pendiente):
        registrar_pendiente(tipo_equipo, identificador, f'CRITICO: {motivo}')


def _cliente_label(cliente_obj) -> str:
    if not cliente_obj:
        return '—'
    return _as_text(getattr(cliente_obj, 'numero_cliente', None)) or f'#{cliente_obj.pk}'


def _equipo_asignado_a_otro_cliente(equipo, cliente_obj) -> bool:
    if not cliente_obj or not hasattr(equipo, 'cliente_id'):
        return False
    cliente_prev_id = getattr(equipo, 'cliente_id', None)
    return bool(cliente_prev_id and cliente_prev_id != cliente_obj.id)


def _intentar_asignar_cliente_equipo(
    equipo,
    tipo_equipo: str,
    cliente_obj,
    registro,
    observacion: str = '',
    registrar_pendiente=None,
) -> bool:
    """
    Un equipo (medidor/módem/SIM) solo puede pertenecer a UN cliente.
    Si ya está en otro: ALERTA CRÍTICA y NO se reasigna (corrección manual).
    Si está libre o ya es del mismo cliente: se puede asignar/confirmar.
    """
    if not cliente_obj or not hasattr(equipo, 'cliente_id'):
        return False

    if _equipo_asignado_a_otro_cliente(equipo, cliente_obj):
        from clientes.models import Cliente

        cliente_prev = Cliente.objects.filter(pk=equipo.cliente_id).only('id', 'numero_cliente').first()
        _registrar_alerta_critica_asignacion(
            registro,
            tipo_equipo,
            _identificador_equipo(equipo, tipo_equipo),
            (
                f'Equipo ya asignado al cliente {_cliente_label(cliente_prev)}. '
                f'MoreApp lo reportó para {_cliente_label(cliente_obj)}. '
                f'NO se reasignó automáticamente: revisar y corregir manualmente.'
            ),
            contexto=observacion,
            registrar_pendiente=registrar_pendiente,
        )
        return False

    if getattr(equipo, 'cliente_id', None) != cliente_obj.id:
        equipo.cliente = cliente_obj
        return True
    return False


def _asignar_medidor_actual_si_disponible(cliente_obj, medidor, registro, registrar_pendiente=None) -> bool:
    """
    Asigna medidor_actual solo si está libre (nadie más lo tiene).
    Si hay conflicto: ALERTA CRÍTICA y NO modifica nada (sin liberar/reasignar).
    Nunca deja escapar IntegrityError: el sync no debe caer en 500.
    """
    from django.db import DatabaseError, IntegrityError, transaction
    from clientes.models import Cliente

    if not cliente_obj or not medidor:
        return False

    if cliente_obj.medidor_actual_id == medidor.pk:
        return False

    # Si el medidor ya pertenece (FK) a otro cliente, no tocar medidor_actual
    if _equipo_asignado_a_otro_cliente(medidor, cliente_obj):
        return False

    otro = (
        Cliente.objects.filter(medidor_actual_id=medidor.pk)
        .exclude(pk=cliente_obj.pk)
        .only('id', 'numero_cliente')
        .first()
    )
    if otro:
        _registrar_alerta_critica_asignacion(
            registro,
            'MEDIDOR',
            _identificador_equipo(medidor, 'MEDIDOR'),
            (
                f'Ya es medidor_actual del cliente {_cliente_label(otro)}. '
                f'No se asignó a {_cliente_label(cliente_obj)}. Corregir manualmente.'
            ),
            registrar_pendiente=registrar_pendiente,
        )
        return False

    # Asignar solo si sigue libre. Sin liberar a terceros (regla: sin auto-corrección).
    try:
        with transaction.atomic():
            if Cliente.objects.filter(medidor_actual_id=medidor.pk).exclude(pk=cliente_obj.pk).exists():
                _registrar_alerta_critica_asignacion(
                    registro,
                    'MEDIDOR',
                    _identificador_equipo(medidor, 'MEDIDOR'),
                    (
                        f'Ya es medidor_actual de otro cliente. '
                        f'No se asignó a {_cliente_label(cliente_obj)}. Corregir manualmente.'
                    ),
                    registrar_pendiente=registrar_pendiente,
                )
                return False
            Cliente.objects.filter(pk=cliente_obj.pk).update(medidor_actual_id=medidor.pk)
        cliente_obj.medidor_actual_id = medidor.pk
        return True
    except (IntegrityError, DatabaseError) as exc:
        logger.exception(
            'Error asignando medidor_actual medidor_id=%s cliente_id=%s: %s',
            medidor.pk,
            cliente_obj.pk,
            exc,
        )
        _registrar_alerta_critica_asignacion(
            registro,
            'MEDIDOR',
            _identificador_equipo(medidor, 'MEDIDOR'),
            (
                f'Conflicto de medidor_actual al asignar a {_cliente_label(cliente_obj)}. '
                f'NO se modificó automáticamente.'
            ),
            registrar_pendiente=registrar_pendiente,
        )
        return False


def _registrar_bloqueo_operativo(
    registro,
    tipo_equipo: str,
    identificador: str,
    motivo: str,
    contexto: str = '',
    registrar_pendiente=None,
):
    detalle = f'BLOQUEO_OPERATIVO | {tipo_equipo} {identificador}: {motivo}'
    if contexto:
        detalle += f' | CONTEXTO: {contexto}'
    logger.warning('[MoreApp] Bloqueo operativo: %s', detalle)
    # No es doble trabajo: es regla operativa (p. ej. módem sin medidor).
    _asignar_estado_revision(registro, 'CON_ADVERTENCIA')
    _append_descripcion_alerta(registro, detalle)
    if callable(registrar_pendiente):
        registrar_pendiente(tipo_equipo, identificador, motivo)


def _validar_reglas_operativas_previas(
    equipo,
    tipo_equipo: str,
    estado_obj,
    cliente_obj,
    medidor_asociado,
    registro,
    observacion: str = '',
    registrar_pendiente=None,
) -> bool:
    """Reglas operativas antes de aceptar cambios de estado/custodia."""
    identificador = _identificador_equipo(equipo, tipo_equipo)

    # Regla 1: trazabilidad mínima para pasar a Instalado (flexible para equipos en bodega).
    if _es_estado_instalado(estado_obj):
        if not _equipo_puede_instalar_desde_moreapp(equipo, tipo_equipo, estado_obj, cliente_obj):
            _registrar_bloqueo_operativo(
                registro,
                tipo_equipo,
                identificador,
                'No se puede instalar: el equipo ya está instalado en otro cliente o sin trazabilidad.',
                contexto=observacion,
                registrar_pendiente=registrar_pendiente,
            )
            return False

    # Regla 2: SIM no puede reasignarse si ya estaba instalada en otro cliente.
    if tipo_equipo == 'SIM' and _es_estado_instalado(getattr(equipo, 'estado_inventario', None)):
        if cliente_obj and getattr(equipo, 'cliente_id', None) and equipo.cliente_id != cliente_obj.id:
            _registrar_bloqueo_operativo(
                registro,
                tipo_equipo,
                identificador,
                f'SIM instalada en otro cliente ({equipo.cliente_id}); no se reasigna automáticamente a {cliente_obj.id}.',
                contexto=observacion,
                registrar_pendiente=registrar_pendiente,
            )
            return False

    # Regla 3: compatibilidad módem/medidor en instalación.
    if tipo_equipo == 'MODEM' and _es_estado_instalado(estado_obj):
        if medidor_asociado and hasattr(medidor_asociado, 'refresh_from_db'):
            medidor_asociado.refresh_from_db()
        if not medidor_asociado:
            _registrar_bloqueo_operativo(
                registro,
                tipo_equipo,
                identificador,
                'No se puede instalar módem sin medidor asociado.',
                contexto=observacion,
                registrar_pendiente=registrar_pendiente,
            )
            return False
        if not _es_estado_instalado(getattr(medidor_asociado, 'estado_inventario', None)):
            _registrar_bloqueo_operativo(
                registro,
                tipo_equipo,
                identificador,
                'Módem no puede quedar instalado con medidor no instalado.',
                contexto=observacion,
                registrar_pendiente=registrar_pendiente,
            )
            return False

    return True


def _actualizar_equipo_operativo(equipo, tipo_equipo: str, estado_obj, cliente_obj, observacion: str,
                                 registro, medidor_asociado=None, ip_dejada: str = '', puerto: str = '',
                                 registrar_pendiente=None, responsable_movimiento=None,
                                 referencia_ot: str = ''):
    cambios = []
    # Guardar ubicación/estado ANTES de mutar: el movimiento debe mostrar el trayecto real
    # (p. ej. Bodega → Instalado en cliente), no Instalado → Instalado.
    ubicacion_previa = getattr(equipo, 'ubicacion_actual', None)
    estado_previo_nombre = ''
    estado_previo = getattr(equipo, 'estado_inventario', None)
    if estado_previo:
        estado_previo_nombre = _as_text(getattr(estado_previo, 'nombre', '')) or ''

    if not _validar_reglas_operativas_previas(
        equipo,
        tipo_equipo,
        estado_obj,
        cliente_obj,
        medidor_asociado,
        registro,
        observacion=observacion,
        registrar_pendiente=registrar_pendiente,
    ):
        return False

    # Si el equipo ya pertenece a otro cliente: alerta crítica y NO se toca ese equipo.
    if _equipo_asignado_a_otro_cliente(equipo, cliente_obj):
        from clientes.models import Cliente

        cliente_prev = Cliente.objects.filter(pk=equipo.cliente_id).only('id', 'numero_cliente').first()
        _registrar_alerta_critica_asignacion(
            registro,
            tipo_equipo,
            _identificador_equipo(equipo, tipo_equipo),
            (
                f'Ya instalado/asignado en cliente {_cliente_label(cliente_prev)}. '
                f'MoreApp lo reportó para {_cliente_label(cliente_obj)}. '
                f'Sin cambios automáticos: corregir manualmente.'
            ),
            contexto=observacion,
            registrar_pendiente=registrar_pendiente,
        )
        return False

    conflicto = _validar_conflicto_instalacion(equipo, tipo_equipo, cliente_obj)
    if conflicto:
        _registrar_alerta_critica_asignacion(
            registro,
            tipo_equipo,
            _identificador_equipo(equipo, tipo_equipo),
            conflicto + ' — sin reasignación automática; modificar manualmente.',
            contexto=observacion,
            registrar_pendiente=registrar_pendiente,
        )
        return False

    if estado_obj and getattr(equipo, 'estado_inventario_id', None) != estado_obj.id:
        equipo.estado_inventario = estado_obj
        cambios.append('estado_inventario')

    es_retiro = bool(estado_obj) and 'retir' in _normalizar_texto(getattr(estado_obj, 'nombre', ''))
    es_instalacion = _es_estado_instalado(estado_obj)

    # La ubicación destino la aplica _registrar_movimiento_equipo (después de
    # registrar origen=ubicacion_previa). Aquí solo liberamos FKs en retiro.
    if es_retiro:
        if getattr(equipo, 'cliente_id', None):
            equipo.cliente = None
            cambios.append('cliente')
        if tipo_equipo == 'MEDIDOR':
            from clientes.models import Cliente as _Cliente
            _Cliente.objects.filter(medidor_actual=equipo).update(medidor_actual=None)
        if tipo_equipo in ('SIM', 'MODEM') and getattr(equipo, 'medidor_id', None):
            equipo.medidor = None
            cambios.append('medidor')
    elif _intentar_asignar_cliente_equipo(
        equipo,
        tipo_equipo,
        cliente_obj,
        registro,
        observacion=observacion,
        registrar_pendiente=registrar_pendiente,
    ):
        cambios.append('cliente')

    if tipo_equipo == 'SIM':
        if medidor_asociado and equipo.medidor_id != medidor_asociado.id:
            equipo.medidor = medidor_asociado
            cambios.append('medidor')
        if ip_dejada and getattr(equipo, 'direccion_ip', '') != ip_dejada:
            equipo.direccion_ip = ip_dejada
            cambios.append('direccion_ip')
        if ip_dejada and getattr(equipo, 'ip_fija', None) != ip_dejada:
            equipo.ip_fija = ip_dejada
            cambios.append('ip_fija')

        # Limpiar placeholder histórico "MoreApp auto <submission_id>" y, si hay
        # técnico real, usar su nombre en Entregado a / custodia.
        nombre_actual = _as_text(getattr(equipo, 'entregado_a_nombre', ''))
        nombre_tecnico = ''
        if responsable_movimiento and getattr(responsable_movimiento, 'rol', None) == 'TECNICO':
            nombre_tecnico = _as_text(getattr(responsable_movimiento, 'nombre_interno', ''))
            if getattr(equipo, 'en_custodia_de_id', None) != responsable_movimiento.id:
                equipo.en_custodia_de = responsable_movimiento
                cambios.append('en_custodia_de')
        if nombre_actual.startswith('MoreApp auto') or (not nombre_actual and nombre_tecnico):
            nuevo_nombre = nombre_tecnico
            if nombre_actual != nuevo_nombre:
                equipo.entregado_a_nombre = nuevo_nombre
                cambios.append('entregado_a_nombre')

    if tipo_equipo == 'MODEM':
        if medidor_asociado and equipo.medidor_id != medidor_asociado.id:
            equipo.medidor = medidor_asociado
            cambios.append('medidor')
        if ip_dejada and getattr(equipo, 'ip', '') != ip_dejada:
            equipo.ip = ip_dejada
            cambios.append('ip')
        if puerto and getattr(equipo, 'puerto', '') != puerto:
            equipo.puerto = puerto
            cambios.append('puerto')

    # medidor_actual solo se toca al instalar; en retiro ya se liberó arriba.
    if (
        tipo_equipo == 'MEDIDOR'
        and cliente_obj
        and es_instalacion
        and cliente_obj.medidor_actual_id != equipo.id
    ):
        _asignar_medidor_actual_si_disponible(
            cliente_obj,
            equipo,
            registro,
            registrar_pendiente=registrar_pendiente,
        )

    # Si no hay cambios de campos pero sí hay cambio de ubicación implícito
    # (p. ej. ya Instalado en otro sitio → Cliente), igual hay que mover.
    necesita_movimiento_ubicacion = False
    if es_instalacion:
        destino_esperado = _obtener_o_crear_ubicacion('CLIENTE', 'Instalado en cliente')
        if getattr(ubicacion_previa, 'id', None) != destino_esperado.id:
            necesita_movimiento_ubicacion = True
    elif es_retiro:
        destino_esperado = _obtener_o_crear_ubicacion('BODEGA_DELCO', 'Bodega Principal')
        if getattr(ubicacion_previa, 'id', None) != destino_esperado.id:
            necesita_movimiento_ubicacion = True

    if not cambios and not necesita_movimiento_ubicacion:
        return False

    if cambios:
        # Quitar duplicados preservando orden (update_fields no admite repeats)
        cambios = list(dict.fromkeys(cambios))
        equipo.save(update_fields=cambios)

    from inventario.models import MovimientoInventario

    estado_nuevo_nombre = _as_text(getattr(estado_obj, 'nombre', '')) if estado_obj else ''
    if estado_previo_nombre or estado_nuevo_nombre:
        observacion_mov = (
            f'{observacion} | Estado: '
            f'{estado_previo_nombre or "-"} -> {estado_nuevo_nombre or "-"}'
        )
    else:
        observacion_mov = observacion

    # Dedupe contra el texto que realmente se persiste (y el legacy sin "| Estado:").
    mov_existente = MovimientoInventario.objects.filter(
        origen_sistema='MOREAPP',
        observacion__in=[observacion_mov, observacion],
    )
    if tipo_equipo == 'MEDIDOR':
        mov_existente = mov_existente.filter(items__medidor=equipo)
    elif tipo_equipo == 'MODEM':
        mov_existente = mov_existente.filter(items__modem=equipo)
    elif tipo_equipo == 'SIM':
        mov_existente = mov_existente.filter(items__simcard=equipo)

    if mov_existente.exists():
        # Ya se registró este mismo cambio (reproceso / doble llamada).
        # Asegurar ubicación destino aunque no se cree otro movimiento.
        if necesita_movimiento_ubicacion and hasattr(equipo, 'ubicacion_actual'):
            if es_instalacion:
                equipo.ubicacion_actual = _obtener_o_crear_ubicacion('CLIENTE', 'Instalado en cliente')
            elif es_retiro:
                equipo.ubicacion_actual = _obtener_o_crear_ubicacion('BODEGA_DELCO', 'Bodega Principal')
            equipo.save(update_fields=['ubicacion_actual'])
        registro.actualizo_equipos = True
        if es_instalacion and cliente_obj:
            _retirar_otros_instalados_en_cliente(
                cliente_obj,
                tipo_equipo,
                equipo,
                observacion,
                registro,
                registrar_pendiente=registrar_pendiente,
                responsable_movimiento=responsable_movimiento,
                medidor_asociado=medidor_asociado,
            )
        return True

    # Tipo operativo real (INSTALACION/RETIRO); origen_sistema=MOREAPP para filtrar.
    _registrar_movimiento_equipo(
        equipo,
        tipo_equipo,
        observacion_mov,
        estado_obj.nombre if estado_obj else '',
        origen_sistema='MOREAPP',
        tipo_override='',
        responsable_override=responsable_movimiento,
        referencia_ot=referencia_ot,
        ubicacion_origen=ubicacion_previa,
    )
    registro.actualizo_equipos = True

    # Si se instaló equipo nuevo, el anterior del mismo tipo en ese cliente pasa a Retirado.
    if es_instalacion and cliente_obj:
        _retirar_otros_instalados_en_cliente(
            cliente_obj,
            tipo_equipo,
            equipo,
            observacion,
            registro,
            registrar_pendiente=registrar_pendiente,
            responsable_movimiento=responsable_movimiento,
            medidor_asociado=medidor_asociado,
        )
    return True


def _retirar_otros_instalados_en_cliente(
    cliente_obj,
    tipo_equipo: str,
    equipo_nuevo,
    observacion_base: str,
    registro,
    registrar_pendiente=None,
    responsable_movimiento=None,
    medidor_asociado=None,
) -> int:
    """Al instalar un equipo nuevo, retira otros del mismo tipo ya instalados en el cliente.

    Ejemplo: módem A instalado en cliente → llega módem B por MoreApp →
    A pasa a Retirado y B a Instalado.
    """
    if not cliente_obj or not equipo_nuevo:
        return 0

    from inventario.models import Medidor, Modem, SimCard

    modelo = {'MEDIDOR': Medidor, 'MODEM': Modem, 'SIM': SimCard}.get(tipo_equipo)
    if not modelo:
        return 0

    estado_retirado = _obtener_estado_por_nombre('Retirado')
    if not estado_retirado:
        return 0

    qs = modelo.objects.filter(cliente=cliente_obj, eliminado=False).exclude(pk=equipo_nuevo.pk)
    # Solo retirar los que estén (o parezcan) instalados
    previos = []
    for eq in qs.select_related('estado_inventario'):
        estado = getattr(eq, 'estado_inventario', None)
        nombre = _normalizar_texto(getattr(estado, 'nombre', '') if estado else '')
        if 'instal' in nombre or not estado:
            previos.append(eq)

    movimientos = 0
    for eq in previos:
        ok = _actualizar_equipo_operativo(
            eq,
            tipo_equipo,
            estado_retirado,
            cliente_obj,
            (
                f'{observacion_base} - retiro automático: se instaló '
                f'{_identificador_equipo(equipo_nuevo, tipo_equipo)} en el mismo cliente'
            ),
            registro,
            medidor_asociado=medidor_asociado if tipo_equipo != 'MEDIDOR' else None,
            registrar_pendiente=registrar_pendiente,
            responsable_movimiento=responsable_movimiento,
        )
        if ok:
            movimientos += 1
    return movimientos


def _aplicar_actualizaciones_operativas(registro, payload: Dict[str, Any], datos_norm: Dict[str, Any], nombre_formulario: str):
    from clientes.models import Cliente
    from inventario.models import Medidor, Modem, SimCard

    campos = payload.get('data', {}) if isinstance(payload.get('data'), dict) else {}
    buscar_cliente = campos.get('buscarCliente', {}) if isinstance(campos.get('buscarCliente'), dict) else {}
    cliente_mantenimiento = campos.get('clienteParaMantenimiento', {}) if isinstance(campos.get('clienteParaMantenimiento'), dict) else {}
    fuentes = [campos, buscar_cliente, cliente_mantenimiento, payload]

    formulario_canonico = _resolver_formulario(nombre_formulario)
    estado_nombre = datos_norm.get('estado') or _valor_campo_fuentes(fuentes, ['estado'])
    contexto_estado = ' '.join(filter(None, [
        _as_text(estado_nombre),
        _as_text(datos_norm.get('actividad')),
        _as_text(datos_norm.get('trabajo')),
        _as_text(datos_norm.get('tipo_incidencia')),
        _as_text(datos_norm.get('trabajo_principal')),
        _as_text(datos_norm.get('diagnostico')),
    ]))
    estado_obj = _resolver_estado_desde_contexto(contexto_estado)

    cliente_codigo = _as_text(datos_norm.get('cliente_codigo') or _valor_campo_fuentes(
        fuentes,
        ['cliente', 'cliente1', 'numero cliente', 'num cliente', 'id cliente'],
    ) or '')

    medidor_serie = _identificador_operativo_util(datos_norm.get('serial_number') or _valor_campo_fuentes(
        fuentes,
        ['medidor', 'serie medidor', 'n serie medidor', 'numero medidor', 'serie', 'medidorsc4i'],
    ) or '')
    medidor_activo_serie = _identificador_operativo_util(datos_norm.get('medidor_activo_numero'))
    medidor_dejado_serie = _identificador_operativo_util(datos_norm.get('medidor_dejado_numero'))
    modem_encontrado_serie = _identificador_operativo_util(datos_norm.get('modem_encontrado'))
    modem_dejado_serie = _identificador_operativo_util(datos_norm.get('modem_dejado') or datos_norm.get('modem_numero'))
    modem_serie = (
        modem_dejado_serie
        or modem_encontrado_serie
        or _identificador_operativo_util(_valor_campo_fuentes(fuentes, ['serie modem', 'modem serie', 'numero modem']))
    )
    sim_ip = _identificador_operativo_util(
        datos_norm.get('ip_dejada') or _valor_campo_fuentes(fuentes, ['ip dejada', 'ip', 'direccion ip']),
        modo='ip',
    )
    puerto_dejado = _limpiar_identificador_operativo(
        datos_norm.get('puerto_dejado') or _valor_campo_fuentes(fuentes, ['puerto dejado', 'puerto'])
    )

    cliente_obj = None
    if cliente_codigo:
        # Solo clientes activos y match exacto (evita soft-deleted e icontains falsos).
        cliente_obj = Cliente.objects.filter(
            activo=True,
            numero_cliente__iexact=cliente_codigo,
        ).first()

    resumen = {
        'formulario_canonico': formulario_canonico,
        'cliente_encontrado': bool(cliente_obj),
        'medidor_encontrado': False,
        'modem_encontrado': False,
        'sim_encontrada': False,
        'estado_aplicado': estado_obj.nombre if estado_obj else '',
        'movimientos_generados': 0,
        'pendientes_revision': [],
        'equipos_reactivados': [],
        'equipos_alta_automatica': [],
        'identificadores_cruce': {
            'medidor_serie': medidor_serie,
            'medidor_activo_serie': medidor_activo_serie,
            'medidor_dejado_serie': medidor_dejado_serie,
            'modem_encontrado_serie': modem_encontrado_serie,
            'modem_dejado_serie': modem_dejado_serie,
            'modem_serie': modem_serie,
            'sim_ip': sim_ip,
            'puerto_dejado': puerto_dejado,
        },
    }

    def _agregar_pendiente(tipo_equipo: str, identificador: str, motivo: str):
        modo = 'ip' if tipo_equipo == 'SIM' and 'ip' in _normalizar_texto(motivo) else 'general'
        ident = _identificador_operativo_util(identificador, modo=modo)
        if not ident:
            return
        resumen['pendientes_revision'].append({
            'tipo_equipo': tipo_equipo,
            'identificador': ident,
            'motivo': motivo,
        })

    def _nota_alta(serie_o_ip: str) -> str:
        return (
            f'Alta automática MoreApp ({formulario_canonico}) '
            f'| id: {serie_o_ip} | submission: {registro.moreapp_submission_id}'
        )

    if cliente_obj:
        cambios_cliente = []
        # STRICT: dirección/comuna a ASCII limpio (evita 1366 en columnas latin1 del host)
        direccion = _as_text_mysql_strict(datos_norm.get('cliente_direccion', ''))
        comuna = _as_text_mysql_strict(datos_norm.get('cliente_comuna', ''))
        if direccion and _as_text_mysql_strict(cliente_obj.direccion) != direccion:
            cliente_obj.direccion = direccion
            cambios_cliente.append('direccion')
        if comuna and _as_text_mysql_strict(cliente_obj.comuna) != comuna:
            cliente_obj.comuna = comuna
            cambios_cliente.append('comuna')
        empresa = _as_text_mysql_strict(datos_norm.get('empresa', ''))
        if empresa and _as_text_mysql_strict(getattr(cliente_obj, 'empresa', '') or '') != empresa:
            cliente_obj.empresa = empresa
            cambios_cliente.append('empresa')
        # No reactivar clientes soft-deleted desde MoreApp.
        if cambios_cliente:
            _sanitizar_cliente_para_mysql(cliente_obj)
            if 'direccion' in cambios_cliente:
                cliente_obj.direccion = _as_text_mysql_strict(cliente_obj.direccion)
            if 'comuna' in cambios_cliente:
                cliente_obj.comuna = _as_text_mysql_strict(cliente_obj.comuna)
            if 'empresa' in cambios_cliente:
                cliente_obj.empresa = _as_text_mysql_strict(cliente_obj.empresa)
            cliente_obj.save(update_fields=cambios_cliente)
            registro.actualizo_cliente = True

    def _revivir_equipo(equipo, etiqueta: str, identificador: str):
        if not equipo or not getattr(equipo, 'eliminado', False):
            return equipo
        equipo.eliminado = False
        if hasattr(equipo, 'fecha_eliminacion'):
            equipo.fecha_eliminacion = None
        if hasattr(equipo, 'eliminado_por_id'):
            equipo.eliminado_por = None
        equipo.save()
        resumen['equipos_reactivados'].append({
            'tipo': etiqueta,
            'identificador': identificador,
        })
        return equipo

    def _buscar_medidor(serie):
        serie = _identificador_operativo_util(serie)
        if not serie:
            return None
        medidor = Medidor.objects.filter(serie__iexact=serie, eliminado=False).first()
        if medidor:
            return medidor
        eliminado = Medidor.objects.filter(serie__iexact=serie, eliminado=True).first()
        return _revivir_equipo(eliminado, 'MEDIDOR', serie)

    def _buscar_modem(serie):
        serie = _identificador_operativo_util(serie)
        if not serie:
            return None
        modem = Modem.objects.filter(serie__iexact=serie, eliminado=False).first()
        if modem:
            return modem

        serie_compacta = _limpiar_identificador_operativo(serie)
        if serie_compacta and serie_compacta != serie:
            modem = Modem.objects.filter(serie__iexact=serie_compacta, eliminado=False).first()
            if modem:
                return modem

        modem = Modem.objects.filter(imei__iexact=serie_compacta or serie, eliminado=False).first()
        if modem:
            return modem

        eliminado = Modem.objects.filter(serie__iexact=serie, eliminado=True).first()
        if not eliminado and serie_compacta and serie_compacta != serie:
            eliminado = Modem.objects.filter(serie__iexact=serie_compacta, eliminado=True).first()
        if not eliminado:
            eliminado = Modem.objects.filter(imei__iexact=serie_compacta or serie, eliminado=True).first()
        return _revivir_equipo(eliminado, 'MODEM', serie)

    def _buscar_sim_por_ip(ip):
        ip = _identificador_operativo_util(ip, modo='ip')
        if not ip:
            return None
        sim = SimCard.objects.filter(direccion_ip__iexact=ip, eliminado=False).first()
        if sim:
            return sim
        sim = SimCard.objects.filter(ip_fija__iexact=ip, eliminado=False).first()
        if sim:
            return sim
        eliminado = (
            SimCard.objects.filter(direccion_ip__iexact=ip, eliminado=True).first()
            or SimCard.objects.filter(ip_fija__iexact=ip, eliminado=True).first()
        )
        return _revivir_equipo(eliminado, 'SIM', ip)

    def _alta_medidor(serie, marca=''):
        serie = _identificador_operativo_util(serie)
        if not serie:
            return None
        bodega = _obtener_o_crear_ubicacion('BODEGA_DELCO', 'Bodega Principal')
        estado_bodega = _obtener_estado_por_nombre('En bodega')
        medidor = Medidor.objects.create(
            serie=serie,
            marca=_as_text(marca) or '',
            tipo_medidor='DIRECTO',
            estado_inventario=estado_bodega,
            ubicacion_actual=bodega,
            observaciones=_nota_alta(serie),
        )
        resumen['equipos_alta_automatica'].append({'tipo': 'MEDIDOR', 'identificador': serie})
        return medidor

    def _alta_modem(serie, marca=''):
        serie = _identificador_operativo_util(serie)
        if not serie:
            return None
        bodega = _obtener_o_crear_ubicacion('BODEGA_DELCO', 'Bodega Principal')
        estado_bodega = _obtener_estado_por_nombre('En bodega')
        modem = Modem.objects.create(
            serie=serie,
            marca=_as_text(marca) or '',
            estado_inventario=estado_bodega,
            ubicacion_actual=bodega,
            observaciones=_nota_alta(serie),
        )
        resumen['equipos_alta_automatica'].append({'tipo': 'MODEM', 'identificador': serie})
        return modem

    def _alta_sim(ip):
        ip = _identificador_operativo_util(ip, modo='ip')
        if not ip:
            return None
        bodega = _obtener_o_crear_ubicacion('BODEGA_DELCO', 'Bodega Principal')
        estado_bodega = _obtener_estado_por_nombre('En bodega')
        # No usar el submission id en "Entregado a": no es un técnico y confunde la revisión.
        sim = SimCard.objects.create(
            direccion_ip=ip,
            ip_fija=ip,
            estado_inventario=estado_bodega,
            ubicacion_actual=bodega,
            entregado_a_nombre='',
        )
        resumen['equipos_alta_automatica'].append({'tipo': 'SIM', 'identificador': ip})
        return sim

    observacion_base = (
        f'Actualización MoreApp ({formulario_canonico}) '
        f'| submission: {registro.moreapp_submission_id}'
    )
    tecnico_moreapp = _as_text(datos_norm.get('tecnico_responsable'))
    responsable_movimiento = _resolver_responsable_moreapp(tecnico_moreapp) or _obtener_responsable_sistema()
    medidor_principal = _buscar_medidor(medidor_serie)
    equipo_vinculo_modem = None
    equipo_vinculo_sim = None

    if cliente_obj and medidor_serie:
        from web.services.validators import validate_meter_terreno_vs_sistema
        for issue in validate_meter_terreno_vs_sistema(medidor_serie, cliente_obj.meter_serial_n_1):
            _agregar_pendiente('MEDIDOR', medidor_serie, issue.message)
            _asignar_estado_revision(registro, 'CON_ADVERTENCIA')
            _append_descripcion_alerta(registro, issue.message)

    if formulario_canonico == 'REGISTRO_MEDIDORES_TELEMETRIA_V3':
        medidor_retirado = _buscar_medidor(medidor_activo_serie)
        if medidor_retirado:
            resumen['medidor_encontrado'] = True
            actualizado = _actualizar_equipo_operativo(
                medidor_retirado,
                'MEDIDOR',
                _obtener_estado_por_nombre('Retirado') or estado_obj,
                cliente_obj,
                f'{observacion_base} - retiro medidor por serie',
                registro,
                registrar_pendiente=_agregar_pendiente,
                responsable_movimiento=responsable_movimiento,
            )
            if actualizado:
                resumen['movimientos_generados'] += 1
        elif medidor_activo_serie:
            _agregar_pendiente('MEDIDOR', medidor_activo_serie, 'Serie de medidor activo (retiro) no encontrada en inventario')

        equipo_reg_modem = None
        equipo_reg_sim = None

        medidor_instalado = _buscar_medidor(medidor_dejado_serie)
        if not medidor_instalado and medidor_dejado_serie:
            medidor_instalado = _alta_medidor(
                medidor_dejado_serie,
                marca=datos_norm.get('marca_medidor_dejado') or datos_norm.get('marca_medidor'),
            )
        if medidor_instalado:
            resumen['medidor_encontrado'] = True
            actualizado = _actualizar_equipo_operativo(
                medidor_instalado,
                'MEDIDOR',
                _obtener_estado_por_nombre('Instalado') or estado_obj,
                cliente_obj,
                f'{observacion_base} - instalación medidor por serie',
                registro,
                registrar_pendiente=_agregar_pendiente,
                responsable_movimiento=responsable_movimiento,
            )
            if actualizado:
                resumen['movimientos_generados'] += 1
            medidor_principal = medidor_instalado
            medidor_principal.refresh_from_db()
        elif medidor_dejado_serie:
            _agregar_pendiente('MEDIDOR', medidor_dejado_serie, 'Serie de medidor dejado no encontrada en inventario')

        modem_instalado = _buscar_modem(modem_dejado_serie)
        if not modem_instalado and modem_dejado_serie:
            modem_instalado = _alta_modem(
                modem_dejado_serie,
                marca=datos_norm.get('marca_modem_dejado') or datos_norm.get('marca_aparato'),
            )
        if modem_instalado:
            resumen['modem_encontrado'] = True
            actualizado = _actualizar_equipo_operativo(
                modem_instalado,
                'MODEM',
                _obtener_estado_por_nombre('Instalado') or estado_obj,
                cliente_obj,
                f'{observacion_base} - instalación módem por serie',
                registro,
                medidor_asociado=medidor_principal,
                ip_dejada=sim_ip,
                puerto=puerto_dejado,
                registrar_pendiente=_agregar_pendiente,
                responsable_movimiento=responsable_movimiento,
            )
            if actualizado:
                resumen['movimientos_generados'] += 1
            equipo_reg_modem = modem_instalado
        elif modem_dejado_serie:
            _agregar_pendiente('MODEM', modem_dejado_serie, 'Serie de módem dejado no encontrada en inventario')

        sim_instalada = _buscar_sim_por_ip(sim_ip)
        if not sim_instalada and sim_ip:
            sim_instalada = _alta_sim(sim_ip)
        if sim_instalada:
            resumen['sim_encontrada'] = True
            actualizado = _actualizar_equipo_operativo(
                sim_instalada,
                'SIM',
                _obtener_estado_por_nombre('Instalado') or estado_obj,
                cliente_obj,
                f'{observacion_base} - instalación SIM por IP',
                registro,
                medidor_asociado=medidor_principal,
                ip_dejada=sim_ip,
                registrar_pendiente=_agregar_pendiente,
                responsable_movimiento=responsable_movimiento,
            )
            if actualizado:
                resumen['movimientos_generados'] += 1
            equipo_reg_sim = sim_instalada
        elif sim_ip:
            _agregar_pendiente('SIM', sim_ip, 'IP dejada de SIM no encontrada en inventario')

        # Punto 8: estado_revision para el bloque REG_MEDIDORES
        if resumen['pendientes_revision'] or registro.alerta_doble_trabajo:
            _asignar_estado_revision(registro, 'CON_ADVERTENCIA')
        else:
            _asignar_estado_revision(registro, 'REVISADO')

        if cliente_obj:
            from ordenes_trabajo.sync import vincular_moreapp_a_orden
            orden_vinculada = vincular_moreapp_a_orden(
                cliente_obj,
                registro_moreapp=registro,
                ruta_carpeta=getattr(registro, 'ruta_carpeta', '') or '',
                medidor=medidor_principal,
                modem=equipo_reg_modem,
                simcard=equipo_reg_sim,
            )
            if orden_vinculada:
                resumen['orden_actualizada'] = orden_vinculada.id
                resumen['orden_estado'] = orden_vinculada.estado
        return resumen

    if medidor_principal:
        resumen['medidor_encontrado'] = True
        actualizado = _actualizar_equipo_operativo(
            medidor_principal,
            'MEDIDOR',
            estado_obj,
            cliente_obj,
            f'{observacion_base} - actualización medidor por serie',
            registro,
            registrar_pendiente=_agregar_pendiente,
            responsable_movimiento=responsable_movimiento,
        )
        if actualizado:
            resumen['movimientos_generados'] += 1
    elif medidor_serie:
        medidor_principal = _alta_medidor(
            medidor_serie,
            marca=datos_norm.get('marca_medidor') or datos_norm.get('marca_aparato'),
        )
        if medidor_principal:
            resumen['medidor_encontrado'] = True
            actualizado = _actualizar_equipo_operativo(
                medidor_principal,
                'MEDIDOR',
                estado_obj,
                cliente_obj,
                f'{observacion_base} - alta y actualización medidor por serie',
                registro,
                registrar_pendiente=_agregar_pendiente,
                responsable_movimiento=responsable_movimiento,
            )
            if actualizado:
                resumen['movimientos_generados'] += 1
        else:
            _agregar_pendiente('MEDIDOR', medidor_serie, 'Serie de medidor no encontrada en inventario')

    modem_encontrado = None
    if formulario_canonico == 'MANTENIMIENTO_TELEMETRIA_V3' and modem_encontrado_serie and modem_dejado_serie:
        modem_retirado = _buscar_modem(modem_encontrado_serie)
        if modem_retirado:
            resumen['modem_encontrado'] = True
            actualizado = _actualizar_equipo_operativo(
                modem_retirado,
                'MODEM',
                _obtener_estado_por_nombre('Retirado') or estado_obj,
                cliente_obj,
                f'{observacion_base} - retiro módem por serie',
                registro,
                medidor_asociado=medidor_principal,
                registrar_pendiente=_agregar_pendiente,
                responsable_movimiento=responsable_movimiento,
            )
            if actualizado:
                resumen['movimientos_generados'] += 1
        else:
            _agregar_pendiente('MODEM', modem_encontrado_serie, 'Serie de módem encontrado (retiro) no existe en inventario')

    if modem_serie:
        modem_encontrado = _buscar_modem(modem_serie)
        if not modem_encontrado:
            modem_encontrado = _alta_modem(
                modem_serie,
                marca=datos_norm.get('marca_modem_dejado') or datos_norm.get('marca_aparato'),
            )
    if modem_encontrado:
        resumen['modem_encontrado'] = True
        estado_modem = estado_obj
        if formulario_canonico == 'MANTENIMIENTO_TELEMETRIA_V3' and modem_dejado_serie:
            estado_modem = _obtener_estado_por_nombre('Instalado') or estado_obj
        actualizado = _actualizar_equipo_operativo(
            modem_encontrado,
            'MODEM',
            estado_modem,
            cliente_obj,
            f'{observacion_base} - actualización módem por serie',
            registro,
            medidor_asociado=medidor_principal,
            ip_dejada=sim_ip,
            puerto=puerto_dejado,
            registrar_pendiente=_agregar_pendiente,
            responsable_movimiento=responsable_movimiento,
        )
        if actualizado:
            resumen['movimientos_generados'] += 1
        equipo_vinculo_modem = modem_encontrado
    elif modem_serie:
        _agregar_pendiente('MODEM', modem_serie, 'Serie de módem no encontrada en inventario')

    sim = _buscar_sim_por_ip(sim_ip)
    if not sim and sim_ip:
        sim = _alta_sim(sim_ip)
    if sim:
        resumen['sim_encontrada'] = True
        estado_sim = estado_obj
        if formulario_canonico in ('MANTENIMIENTO_TELEMETRIA_V3', 'REGISTRO_MEDIDORES_TELEMETRIA_V3') and sim_ip:
            estado_sim = _obtener_estado_por_nombre('Instalado') or estado_obj
        actualizado = _actualizar_equipo_operativo(
            sim,
            'SIM',
            estado_sim,
            cliente_obj,
            f'{observacion_base} - actualización SIM por IP',
            registro,
            medidor_asociado=medidor_principal,
            ip_dejada=sim_ip,
            registrar_pendiente=_agregar_pendiente,
            responsable_movimiento=responsable_movimiento,
        )
        if actualizado:
            resumen['movimientos_generados'] += 1
        equipo_vinculo_sim = sim
    elif sim_ip:
        _agregar_pendiente('SIM', sim_ip, 'IP de SIM no encontrada en inventario')

    # Punto 8: establecer estado_revision según resultados
    if resumen['pendientes_revision']:
        _asignar_estado_revision(registro, 'CON_ADVERTENCIA')
    elif registro.alerta_doble_trabajo:
        _asignar_estado_revision(registro, 'CON_ADVERTENCIA')
    else:
        _asignar_estado_revision(registro, 'REVISADO')

    # Vincular informe entrante con orden de trabajo del cliente
    if cliente_obj:
        from ordenes_trabajo.sync import vincular_moreapp_a_orden
        orden_vinculada = vincular_moreapp_a_orden(
            cliente_obj,
            registro_moreapp=registro,
            ruta_carpeta=getattr(registro, 'ruta_carpeta', '') or '',
            medidor=medidor_principal,
            modem=equipo_vinculo_modem,
            simcard=equipo_vinculo_sim,
        )
        if orden_vinculada:
            resumen['orden_actualizada'] = orden_vinculada.id
            resumen['orden_estado'] = orden_vinculada.estado

    return resumen



def _extraer_lectura(data: dict, info: dict, meta: dict) -> Dict[str, Any]:
    """
    Extrae campos del formulario Lectura usando acceso directo a las claves
    reales del JSON (sin búsqueda por alias genéricos).

    Campos del formulario:
      data.cliente                            → código cliente
      data.clienteParaMantenimiento.CLIENTE   → código cliente (alt)
      data.clienteParaMantenimiento.MEDIDORSC4I   → serie medidor
      data.clienteParaMantenimiento.SNMANUFACTURER2 → serie fabricante
      data.clienteParaMantenimiento.MARCA     → marca medidor
      data.clienteParaMantenimiento.CLIENTE2  → nombre cliente
      data.clienteParaMantenimiento.DIRECCIONDESUMINISTRO → dirección
      data.clienteParaMantenimiento.COMUNA    → comuna
      data.clienteParaMantenimiento.TIPOSUMINISTRO → tipo suministro
      data.estado                             → estado del equipo
      data.tipoDeIncidencia                   → tipo de trabajo / incidencia
      data.formatoCsv                         → indica si hay CSV
      data.nombreDelContacto                  → nombre contacto en terreno
      data.telefono                           → teléfono contacto
      data.correo                             → correo contacto
      data.tecnicoResponsable.NOMBRES         → técnico responsable
      data.observacin                         → observación (typo en formulario)
      data.fechaDeLaVisita                    → fecha de la visita
      data.location                           → geolocalización
    """
    campos = data.get('data', {})
    cli_man = campos.get('clienteParaMantenimiento', {})
    if not isinstance(cli_man, dict):
        cli_man = {}
    tecnico = campos.get('tecnicoResponsable', {})
    if not isinstance(tecnico, dict):
        tecnico = {}
    location = campos.get('location', {})
    location_str = location.get('formattedValue', '') if isinstance(location, dict) else _as_text(location)

    return {
        'form_name': info.get('formName', ''),
        'formulario_canonico': 'LECTURA',
        'fecha_registro': meta.get('registrationDate', ''),
        # Serie del medidor: primero MEDIDORSC4I, fallback SN del fabricante
        'serial_number': _as_text(cli_man.get('MEDIDORSC4I') or cli_man.get('SNMANUFACTURER2')),
        'marca_medidor': _as_text(cli_man.get('MARCA')),
        'empresa': '',
        # Tipo de incidencia es la actividad principal en este formulario
        'actividad': _as_text(campos.get('tipoDeIncidencia')),
        'estado': _as_text(campos.get('estado')),
        # Código de cliente: campo raíz tiene prioridad; CLIENTE en el dict es alternativa
        'cliente_codigo': _as_text(campos.get('cliente') or cli_man.get('CLIENTE')),
        # Nombre legible del cliente
        'cliente_nombre': _as_text(cli_man.get('CLIENTE2')),
        'cliente_direccion': _as_text(cli_man.get('DIRECCIONDESUMINISTRO')),
        'cliente_comuna': _as_text(cli_man.get('COMUNA')),
        'trabajo': _as_text(campos.get('tipoDeIncidencia')),
        'tipo_suministro': _as_text(cli_man.get('TIPOSUMINISTRO')),
        'formato_csv': _as_text(campos.get('formatoCsv')),
        'contacto_nombre': _as_text(campos.get('nombreDelContacto')),
        'contacto_telefono': _as_text(campos.get('telefono')),
        'contacto_correo': _as_text(campos.get('correo')),
        'con_sim': '',
        'tipo_telemetria': '',
        'tecnico_responsable': _as_text(tecnico.get('NOMBRES')),
        'tecnico_asistente': '',
        # "observacin" es el nombre real del campo en el formulario (falta la 'o')
        'observacion': _as_text(campos.get('observacin')),
        'fecha_trabajo': _as_text(campos.get('fechaDeLaVisita')),
        'location': location_str,
    }


def _extraer_mantenimiento(data: dict, info: dict, meta: dict) -> Dict[str, Any]:
    """
    Extrae campos del formulario Mantenimiento Telemetria V3 usando
    acceso directo a las claves reales del JSON.
    """
    campos = data.get('data', {})
    cli_man = campos.get('clienteParaMantenimiento', {})
    if not isinstance(cli_man, dict):
        cli_man = {}

    tecnico = campos.get('tecnicoResponsable', {})
    if not isinstance(tecnico, dict):
        tecnico = {}
    asistente = campos.get('tecnicoAsistente', {})
    if not isinstance(asistente, dict):
        asistente = {}

    location = campos.get('location', {})
    location_str = location.get('formattedValue', '') if isinstance(location, dict) else _as_text(location)

    return {
        'form_name': info.get('formName', ''),
        'formulario_canonico': 'MANTENIMIENTO_TELEMETRIA_V3',
        'fecha_registro': meta.get('registrationDate', ''),
        'serial_number': _as_text(cli_man.get('NROAPARATO')),
        'empresa': '',
        'actividad': _as_text(campos.get('tipoDeIncidencia')),
        'estado': _as_text(campos.get('estado')),
        'cliente_codigo': _as_text(campos.get('cliente') or cli_man.get('NROCLIENTE')),
        'cliente_nombre': _as_text(cli_man.get('NOMBRE')),
        'cliente_direccion': _as_text(cli_man.get('DIRECCION')),
        'cliente_comuna': _as_text(cli_man.get('COMUNA')),
        'trabajo': _as_text(campos.get('tipoDeIncidencia')),
        'con_sim': '',
        'tipo_telemetria': '',
        'tecnico_responsable': _as_text(tecnico.get('NOMBRES')),
        'tecnico_asistente': _as_text(asistente.get('NOMBRES')),
        'observacion': _as_text(campos.get('observacion')),
        'fecha_trabajo': _as_text(campos.get('fechaDeLaVisita')),
        'location': location_str,
        'nro_cliente': _as_text(cli_man.get('NROCLIENTE')),
        'nro_aparato': _as_text(cli_man.get('NROAPARATO')),
        'marca_aparato': _as_text(cli_man.get('MARCAAPARATO')),
        'tipo_modelo': _as_text(cli_man.get('TIPOMODELO')),
        'descripcion_prop': _as_text(cli_man.get('descripcionprop')),
        'expr_1008': _as_text(cli_man.get('expr1008')),
        'sector': _as_text(cli_man.get('SECTOR')),
        'cod_tarifa': _as_text(cli_man.get('CODTARIFA')),
        'proceso_lectura': _as_text(cli_man.get('PROCESODELECTURA')),
        'amperes': _as_text(cli_man.get('AMPERES')),
        'proteccion_empalme': _as_text(cli_man.get('PROTECCIONEMPALME')),
        'potencia_contratada': _as_text(cli_man.get('POTENCIACONTRATADA')),
        'tipo_empalme': _as_text(cli_man.get('TIPOEMPALME')),
        'contacto_nombre': _as_text(campos.get('nombreDelContacto')),
        'contacto_telefono': _as_text(campos.get('telefono')),
        'contacto_correo': _as_text(campos.get('correo')),
        'datos_medidor_correctos': _as_text(campos.get('datosDelMedidorSonCorrectos')),
        'diagnostico': _as_text(campos.get('diagnostico')),
        'trabajo_principal': _as_text(campos.get('trabajoPrincipal')),
        'cliente_consumo_no_registrado': _as_text(campos.get('clienteTieneConsumoDeEnergiaNORegistrado')),
        'modem_encontrado': _as_text(campos.get('numeroDeModemEncontrado')),
        'modem_dejado': _as_text(campos.get('numeroModemDejado')),
        'marca_modem_dejado': _as_text(campos.get('marcaDeModemDejado')),
        'ip_dejada': _as_text(campos.get('iPDejada')),
        'puerto_dejado': _as_text(campos.get('puertoDejado')),
        'nombre_autoriza': _as_text(campos.get('nombreDeQuienAutoriza')),
    }


def _extraer_registro_medidores_telemetria(data: dict, info: dict, meta: dict) -> Dict[str, Any]:
    """
    Extrae campos del formulario Registro de Medidores y Telemetria V3
    usando acceso directo a las claves reales del JSON.
    """
    campos = data.get('data', {})
    buscar = campos.get('buscarCliente', {})
    if not isinstance(buscar, dict):
        buscar = {}

    tecnico_delco = campos.get('tECNICORESPONSABLE', {})
    if not isinstance(tecnico_delco, dict):
        tecnico_delco = {}
    tecnico_certelec = campos.get('tcnicoResponsableCertelec', {})
    if not isinstance(tecnico_certelec, dict):
        tecnico_certelec = {}
    tecnico_asistente = campos.get('tcnicoAsistente', {})
    if not isinstance(tecnico_asistente, dict):
        tecnico_asistente = {}

    location = campos.get('location', {})
    location_str = location.get('formattedValue', '') if isinstance(location, dict) else _as_text(location)

    numero_medidor_dejado = _as_text(campos.get('numeroDeMedidorDejado'))
    numero_modem = _as_text(campos.get('numeroDeModem1'))

    return {
        'form_name': info.get('formName', ''),
        'formulario_canonico': 'REGISTRO_MEDIDORES_TELEMETRIA_V3',
        'fecha_registro': meta.get('registrationDate', ''),
        'serial_number': numero_medidor_dejado,
        'empresa': _as_text(campos.get('empresa')),
        'actividad': _as_text(campos.get('actividad')),
        'estado': _as_text(campos.get('estado')),
        'cliente_codigo': _as_text(campos.get('cliente') or buscar.get('CLIENTE1')),
        'cliente_nombre': _as_text(buscar.get('NOMBRE')),
        'cliente_direccion': _as_text(buscar.get('DIRECCION')),
        'cliente_comuna': _as_text(buscar.get('COMUNA')),
        'trabajo': _as_text(buscar.get('TRABAJO')),
        'con_sim': _as_text(campos.get('conOSinChip')),
        'tipo_telemetria': _as_text(campos.get('tipoDeTelemetria')),
        'tecnico_responsable': _as_text(tecnico_delco.get('NOMBRES')),
        'tecnico_asistente': _as_text(tecnico_asistente.get('NOMBRES')),
        'observacion': _as_text(campos.get('observacinDelTrabajo')),
        'fecha_trabajo': _as_text(campos.get('fecha')),
        'location': location_str,
        'cliente_1': _as_text(buscar.get('CLIENTE1')),
        'marca_aparato': _as_text(buscar.get('MARCAAPARATO')),
        'modelo_aparato': _as_text(buscar.get('MODELOAPARATO')),
        'nueva_ruta': _as_text(buscar.get('NUEVARUTA')),
        'tipo_incidencia': _as_text(campos.get('tipoDeIncidencia')),
        'contacto_nombre': _as_text(campos.get('nombreDelContacto')),
        'contacto_telefono': _as_text(campos.get('telefono')),
        'contacto_correo': _as_text(campos.get('correo')),
        'medidor_activo_numero': _as_text(campos.get('numeroDeMedidorActivo')),
        'medidor_activo_lectura': _as_text(campos.get('lecturaMedidorActivo')),
        'medidor_reactivo_numero': _as_text(campos.get('numeroDeMedidorReactivo')),
        'medidor_reactivo_lectura': _as_text(campos.get('lecturaDeMedidorReactivo')),
        'demanda_hp': _as_text(campos.get('demandaHoraPuntaEnKwDMHP')),
        'demanda_fp': _as_text(campos.get('demandaFueraPuntaEnKwDMFP')),
        'multiplo_lectura': _as_text(campos.get('mltiploDeLectura')),
        'medidor_dejado_numero': numero_medidor_dejado,
        'modem_numero': numero_modem,
        'modem_encontrado': numero_modem,
        'marca_medidor_dejado': _as_text(campos.get('marcaDeMedidorDejado')),
        'puerto_dejado': _as_text(campos.get('puerto')),
        'ip_dejada': _as_text(campos.get('iPDejada')),
        'proveedor_datos': _as_text(campos.get('proveedorDeDatos')),
        'nombre_autoriza': _as_text(campos.get('nombreDeLaPersonaQueAutorizaCambio')),
        'tecnico_certelec': _as_text(tecnico_certelec.get('nombres')),
    }


def _extraer_datos_normalizados(data: dict) -> Dict[str, Any]:
    """
    Extrae los campos operativos clave de un registration.json
    para consulta rápida en Reportes sin tener que parsear el JSON completo.
    Despacha a una función específica según el formulario detectado.
    """
    info = data.get('info', {})
    meta = data.get('meta', {})
    campos = data.get('data', {})

    nombre_formulario = info.get('formName', '')
    formulario_canonico = _resolver_formulario(nombre_formulario)

    # --- Formulario específico: Lectura ---
    if formulario_canonico == 'LECTURA':
        return _extraer_lectura(data, info, meta)

    # --- Formulario específico: Mantenimiento Telemetria V3 ---
    if formulario_canonico == 'MANTENIMIENTO_TELEMETRIA_V3':
        return _extraer_mantenimiento(data, info, meta)

    # --- Formulario específico: Registro de Medidores y Telemetria V3 ---
    if formulario_canonico == 'REGISTRO_MEDIDORES_TELEMETRIA_V3':
        return _extraer_registro_medidores_telemetria(data, info, meta)

    # --- Formularios genéricos (Mantenimiento, Registro de Medidores, etc.) ---
    buscar_cliente = campos.get('buscarCliente', {})
    cliente_mantenimiento = campos.get('clienteParaMantenimiento', {})
    fuentes = [campos, buscar_cliente, cliente_mantenimiento, data]

    return {
        'form_name': nombre_formulario,
        'formulario_canonico': formulario_canonico,
        'fecha_registro': meta.get('registrationDate', ''),
        'serial_number': (
            meta.get('serialNumber')
            or _valor_campo_fuentes(fuentes, ['serie medidor', 'medidor', 'numero medidor', 'serie'])
        ),
        'empresa': campos.get('empresa', ''),
        'actividad': _valor_campo_fuentes(fuentes, ['actividad', 'trabajo']) or campos.get('actividad', ''),
        'estado': _valor_campo_fuentes(fuentes, ['estado']),
        'cliente_codigo': _as_text(_valor_campo_fuentes(
            fuentes,
            ['cliente', 'cliente1', 'numero cliente', 'num cliente', 'nrocliente', 'cliente2'],
        )),
        'cliente_nombre': _as_text(_valor_campo_fuentes(fuentes, ['nombre', 'cliente2'])),
        'cliente_direccion': _as_text(_valor_campo_fuentes(fuentes, ['direccion', 'direcciondesuministro'])),
        'cliente_comuna': _as_text(_valor_campo_fuentes(fuentes, ['comuna'])),
        'trabajo': _as_text(_valor_campo_fuentes(fuentes, ['trabajo', 'tiposuministro'])),
        'con_sim': campos.get('conOSinChip', ''),
        'tipo_telemetria': campos.get('tipoDeTelemetria', ''),
        'tecnico_responsable': (
            _as_text(_valor_campo_fuentes(
                fuentes,
                ['tecnicoresponsable', 'tecnico responsable', 'tecnico'],
            ))
            or campos.get('tECNICORESPONSABLE', {}).get('NOMBRES', '')
            or campos.get('tecnicoResponsable', {}).get('NOMBRES', '')
            or campos.get('tcnicoResponsableCertelec', {}).get('nombres', '')
        ),
        'tecnico_asistente': (
            campos.get('tcnicoAsistente', {}).get('NOMBRES', '')
            or campos.get('tecnicoAsistente', {}).get('NOMBRES', '')
        ),
        'observacion': _as_text(_valor_campo_fuentes(fuentes, ['observacion', 'observacion del trabajo'])),
        'fecha_trabajo': _as_text(_valor_campo_fuentes(fuentes, ['fecha', 'fecha de la visita'])),
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

    cliente = _as_text(datos.get('cliente_codigo', ''))
    trabajo = _as_text(datos.get('trabajo', '')) or _as_text(datos.get('actividad', ''))

    if not cliente or not trabajo:
        return False, ''

    ahora = timezone.now()
    ventana_alta = ahora - timedelta(days=1)
    ventana_duplicado = ahora - timedelta(days=14)

    # Regla sobre órdenes de trabajo: misma asignación al cliente en 14 días
    from ordenes_trabajo.models import OrdenTrabajo
    from ordenes_trabajo.utils import detectar_duplicado_orden

    cliente_obj = None
    if cliente:
        from clientes.models import Cliente
        cliente_obj = Cliente.objects.filter(
            activo=True,
            numero_cliente__iexact=cliente,
        ).first()

    if cliente_obj:
        tiene_dup_orden, desc_orden = detectar_duplicado_orden(cliente_obj)
        if tiene_dup_orden:
            return True, desc_orden

    # Excluir el propio registro (puede que ya exista como DUPLICADO)
    candidatos = IntegracionMoreApp.objects.exclude(
        moreapp_submission_id=submission_id
    ).filter(
        fecha_recepcion__gte=ventana_duplicado,
    ).exclude(
        estado_sincronizacion='DUPLICADO'
    )

    for candidato in candidatos:
        datos_c = candidato.datos_procesados
        if not datos_c:
            continue
        cliente_c = _as_text(datos_c.get('cliente_codigo', ''))
        trabajo_c = (_as_text(datos_c.get('trabajo', ''))
                 or _as_text(datos_c.get('actividad', '')))

        if cliente_c == cliente and trabajo_c == trabajo:
            if candidato.fecha_recepcion >= ventana_alta:
                severidad = 'Alta (mismo día)'
            else:
                severidad = 'Media (últimos 14 días)'

            desc = (
                f'Posible doble trabajo — Cliente: {cliente} | '
                f'Actividad: {trabajo} | Severidad: {severidad} | '
                f'Registro anterior: #{candidato.numero_correlativo} '
                f'({candidato.fecha_recepcion.strftime("%d/%m/%Y %H:%M")})'
            )
            return True, desc

    return False, ''


def leer_carpetas(
    base_dir: Optional[str] = None,
    dry_run: bool = False,
    reprocesar_duplicados: Optional[bool] = None,
    max_archivos: Optional[int] = None,
    max_segundos: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Recorre la estructura de carpetas de MoreApp y registra los submissions nuevos.

    Estructura esperada:
        {base_dir}/{customerId}/{formName}/{correlativo}/registration.json

    Args:
        base_dir: Ruta raíz donde están los registros. Si es None usa DEFAULT o settings.
        dry_run:  Si True, detecta carpetas pero no guarda en BD.
        reprocesar_duplicados: Si False, un id ya existente se omite sin updates operativos.
        max_archivos: Tope de registration.json a abrir en esta corrida (None = sin tope).
        max_segundos: Tope de tiempo de la corrida (None = sin tope).

    Returns:
        Dict con estadísticas: nuevos, duplicados, errores, alertas, omitidos.
    """
    import time

    base = base_dir or getattr(settings, 'MOREAPP_REGISTROS_DIR', DEFAULT_REGISTROS_BASE)
    incremental_enabled = bool(getattr(settings, 'MOREAPP_INCREMENTAL_SCAN_ENABLED', True)) and not dry_run
    lookback = int(getattr(settings, 'MOREAPP_INCREMENTAL_LOOKBACK', 2) or 2)
    if lookback < 0:
        lookback = 0
    first_scan_tail = int(getattr(settings, 'MOREAPP_FIRST_SCAN_TAIL', 40) or 40)
    if first_scan_tail < 1:
        first_scan_tail = 1

    if reprocesar_duplicados is None:
        reprocesar_duplicados = True

    t0 = time.monotonic()
    detener = False
    motivo_corte = ''

    stats = {
        'base_dir': base,
        'modo': 'incremental' if incremental_enabled else 'full',
        'nuevos': 0,
        'duplicados': 0,
        'alertas': 0,
        'errores': 0,
        'omitidos': 0,
        'carpetas_revisadas': 0,
        'incompleto': False,
        'motivo_corte': '',
        'detalle': [],
    }

    if not os.path.isdir(base):
        logger.warning('Directorio base no encontrado: %s', base)
        stats['detalle'].append({'error': f'Directorio no encontrado: {base}'})
        return stats

    estado_sync = _cargar_estado_sync(base) if incremental_enabled else {'version': 1, 'forms': {}}

    # Recorrer: base / customerId / formName / correlativo /
    for customer_id in os.listdir(base):
        if detener:
            break
        customer_path = os.path.join(base, customer_id)
        if not os.path.isdir(customer_path):
            continue

        for form_name in os.listdir(customer_path):
            if detener:
                break
            form_path = os.path.join(customer_path, form_name)
            if not os.path.isdir(form_path):
                continue

            clave_form = _clave_estado_form(customer_id, form_name)
            ultimo_correlativo = None
            if incremental_enabled:
                info_form = estado_sync.get('forms', {}).get(clave_form, {})
                if isinstance(info_form, dict):
                    ultimo_correlativo = info_form.get('last_correlativo')

            correlativos = sorted(os.listdir(form_path), key=lambda x: int(x) if x.isdigit() else 0)
            if incremental_enabled and isinstance(ultimo_correlativo, int):
                umbral = max(1, ultimo_correlativo - lookback + 1)
                correlativos = [
                    c for c in correlativos
                    if (not c.isdigit()) or int(c) >= umbral
                ]
            elif len(correlativos) > first_scan_tail:
                # Sin estado previo: no barrer años de histórico en una sola request HTTP
                correlativos = correlativos[-first_scan_tail:]

            max_exitoso_form = ultimo_correlativo if isinstance(ultimo_correlativo, int) else None

            for correlativo in correlativos:
                if max_archivos is not None and stats['carpetas_revisadas'] >= max_archivos:
                    detener = True
                    motivo_corte = f'límite de archivos ({max_archivos})'
                    break
                if max_segundos is not None and (time.monotonic() - t0) >= float(max_segundos):
                    detener = True
                    motivo_corte = f'límite de tiempo ({max_segundos}s)'
                    break

                correlativo_path = os.path.join(form_path, correlativo)
                json_path = os.path.join(correlativo_path, 'registration.json')

                if not os.path.isfile(json_path):
                    stats['omitidos'] += 1
                    continue

                stats['carpetas_revisadas'] += 1

                try:
                    resultado = _procesar_json(
                        json_path=json_path,
                        ruta_carpeta=correlativo_path,
                        numero_correlativo=int(correlativo) if correlativo.isdigit() else None,
                        dry_run=dry_run,
                        reprocesar_duplicados=reprocesar_duplicados,
                    )
                except Exception as exc:
                    logger.exception('Error no controlado procesando %s', json_path)
                    resultado = {
                        'json_path': json_path,
                        'ruta_carpeta': correlativo_path,
                        'correlativo': int(correlativo) if correlativo.isdigit() else None,
                        'resultado': 'error',
                        'submission_id': None,
                        'alerta': True,
                        'mensaje': f'Error no controlado: {exc}',
                    }
                # Evitar respuesta enorme: solo errores/alertas/nuevos en detalle
                if (
                    resultado.get('resultado') != 'duplicado'
                    or resultado.get('alerta')
                    or len(stats['detalle']) < 30
                ):
                    stats['detalle'].append(resultado)

                if resultado['resultado'] == 'nuevo':
                    stats['nuevos'] += 1
                    if resultado.get('alerta'):
                        stats['alertas'] += 1
                elif resultado['resultado'] in ('duplicado', 'eliminado'):
                    stats['duplicados'] += 1
                    if resultado.get('alerta'):
                        stats['alertas'] += 1
                elif resultado['resultado'] == 'error':
                    stats['errores'] += 1

                if correlativo.isdigit() and resultado['resultado'] in ('nuevo', 'duplicado', 'eliminado'):
                    c_num = int(correlativo)
                    max_exitoso_form = c_num if max_exitoso_form is None else max(max_exitoso_form, c_num)

            if incremental_enabled and isinstance(max_exitoso_form, int):
                estado_sync.setdefault('forms', {})[clave_form] = {
                    'last_correlativo': max_exitoso_form,
                }

    if incremental_enabled:
        try:
            _guardar_estado_sync(base, estado_sync)
        except Exception:
            logger.exception('No se pudo guardar estado incremental MoreApp')

    if detener:
        stats['incompleto'] = True
        stats['motivo_corte'] = motivo_corte
        stats['modo'] = f"{stats['modo']}+parcial"

    logger.info(
        'Lectura completada (%s) — revisadas=%d nuevos=%d duplicados=%d alertas=%d errores=%d incompleto=%s',
        stats['modo'],
        stats['carpetas_revisadas'],
        stats['nuevos'],
        stats['duplicados'],
        stats['alertas'],
        stats['errores'],
        stats['incompleto'],
    )
    return stats


def _procesar_json(
    json_path: str,
    ruta_carpeta: str,
    numero_correlativo: Optional[int],
    dry_run: bool,
    reprocesar_duplicados: bool = True,
) -> Dict[str, Any]:
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
    existente = IntegracionMoreApp.objects.filter(moreapp_submission_id=submission_id).first()
    if existente:
        # Soft-deleted: no reprocessar ni recrear
        if getattr(existente, 'eliminado', False):
            resultado['resultado'] = 'eliminado'
            resultado['alerta'] = False
            resultado['mensaje'] = (
                f'Registro soft-deleted id={submission_id}; se omite sin recrear'
            )
            return resultado
        # Ruta rápida: evita timeout en sync HTTP al no reaplicar inventario en cada pasada
        if not reprocesar_duplicados:
            resultado['resultado'] = 'duplicado'
            resultado['alerta'] = bool(existente.alerta_doble_trabajo)
            resultado['mensaje'] = f'Ya existe registro con id={submission_id}'
            return resultado
        try:
            datos_norm = _extraer_datos_normalizados(data)
            resumen_operativo = _aplicar_actualizaciones_operativas(
                registro=existente,
                payload=data,
                datos_norm=datos_norm,
                nombre_formulario=nombre_formulario,
            )
            existente.datos_recibidos = data
            existente.datos_procesados = _finalizar_datos_procesados(datos_norm, data, existente, resumen_operativo)
            existente.nombre_formulario = nombre_formulario
            existente.numero_correlativo = numero_correlativo
            existente.ruta_carpeta = ruta_carpeta
            existente.fecha_procesamiento = timezone.now()
            existente.save(
                update_fields=[
                    'datos_recibidos',
                    'datos_procesados',
                    'nombre_formulario',
                    'numero_correlativo',
                    'ruta_carpeta',
                    'fecha_procesamiento',
                    'actualizo_cliente',
                    'actualizo_equipos',
                    'estado_revision',
                    'alerta_doble_trabajo',
                    'descripcion_alerta',
                ]
            )
            resultado['resultado'] = 'duplicado'
            resultado['alerta'] = bool(existente.alerta_doble_trabajo)
            resultado['mensaje'] = (
                existente.descripcion_alerta
                if existente.alerta_doble_trabajo and existente.descripcion_alerta
                else f'Ya existe registro con id={submission_id}'
            )
        except Exception as exc:
            logger.exception('Error reprocesando duplicado MoreApp id=%s', submission_id)
            resultado['resultado'] = 'duplicado'
            resultado['alerta'] = True
            resultado['mensaje'] = f'Ya existe id={submission_id}; error operativo: {exc}'
            try:
                existente.alerta_doble_trabajo = True
                detalle = f'ERROR_SYNC | {exc}'
                _append_descripcion_alerta(existente, detalle)
                _asignar_estado_revision(existente, 'CON_ADVERTENCIA')
                existente.fecha_procesamiento = timezone.now()
                existente.save(
                    update_fields=[
                        'alerta_doble_trabajo',
                        'descripcion_alerta',
                        'estado_revision',
                        'fecha_procesamiento',
                    ]
                )
            except Exception:
                logger.exception('No se pudo guardar alerta en duplicado %s', submission_id)
        logger.info('Duplicado omitido: %s', submission_id)
        return resultado

    # --- Extraer datos normalizados ---
    datos_norm = _extraer_datos_normalizados(data)

    # --- Detección alerta doble trabajo ---
    tiene_alerta, desc_alerta = _detectar_alerta_doble_trabajo(submission_id, datos_norm)

    # --- Guardar en BD (crear primero; updates operativos aparte para no tumbar el sync) ---
    estado = 'ALERTA_REVISION' if tiene_alerta else 'PROCESADO'
    registro = IntegracionMoreApp.objects.create(
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

    resumen_operativo = {}
    try:
        resumen_operativo = _aplicar_actualizaciones_operativas(
            registro=registro,
            payload=data,
            datos_norm=datos_norm,
            nombre_formulario=nombre_formulario,
        )
        registro.datos_procesados = _finalizar_datos_procesados(datos_norm, data, registro, resumen_operativo)
        registro.save(
            update_fields=[
                'datos_procesados',
                'actualizo_cliente',
                'actualizo_equipos',
                'estado_revision',
                'alerta_doble_trabajo',
                'descripcion_alerta',
            ]
        )
    except Exception as exc:
        logger.exception('Error operativo MoreApp id=%s', submission_id)
        registro.alerta_doble_trabajo = True
        _asignar_estado_revision(registro, 'CON_ADVERTENCIA')
        detalle = f'ERROR_SYNC | {exc}'
        _append_descripcion_alerta(registro, detalle)
        registro.datos_procesados = _finalizar_datos_procesados(datos_norm, data, registro, {'error': str(exc)})
        try:
            registro.save(
                update_fields=[
                    'datos_procesados',
                    'estado_revision',
                    'alerta_doble_trabajo',
                    'descripcion_alerta',
                ]
            )
        except Exception:
            logger.exception('No se pudo guardar alerta operativa id=%s', submission_id)

    resultado['resultado'] = 'nuevo'
    resultado['alerta'] = bool(registro.alerta_doble_trabajo or resumen_operativo.get('pendientes_revision'))
    if registro.descripcion_alerta:
        resultado['mensaje'] = registro.descripcion_alerta
    elif resumen_operativo.get('pendientes_revision'):
        resultado['mensaje'] = f'Pendientes operativos detectados: {len(resumen_operativo.get("pendientes_revision", []))}'
    else:
        resultado['mensaje'] = desc_alerta if tiene_alerta else 'OK'
    logger.info('Registrado: %s (alerta=%s)', submission_id, tiene_alerta)
    return resultado


def procesar_payload_moreapp(payload: Dict[str, Any], ruta_context: str = 'webhook') -> Dict[str, Any]:
    """
    Procesa un payload de MoreApp en tiempo real (sin archivo intermedio).
    """
    from ordenes_trabajo.models import IntegracionMoreApp

    resultado = {
        'json_path': f'({ruta_context})',
        'ruta_carpeta': ruta_context,
        'correlativo': None,
        'resultado': 'error',
        'submission_id': None,
        'alerta': False,
        'mensaje': '',
    }

    data = payload if isinstance(payload, dict) else {}
    if not data:
        resultado['mensaje'] = 'Payload vacío o inválido'
        return resultado

    for campo in CAMPOS_MINIMOS:
        if campo not in data:
            resultado['mensaje'] = f'Campo mínimo faltante: {campo}'
            resultado['resultado'] = 'error'
            _guardar_error('', ruta_context, None, 'ERROR_JSON', resultado['mensaje'], data)
            return resultado

    submission_id = data.get('id', '')
    resultado['submission_id'] = submission_id
    nombre_formulario = data.get('info', {}).get('formName', '')

    existente = IntegracionMoreApp.objects.filter(moreapp_submission_id=submission_id).first()
    if existente:
        # Soft-deleted: no reprocessar ni recrear vía webhook
        if getattr(existente, 'eliminado', False):
            resultado['resultado'] = 'eliminado'
            resultado['alerta'] = False
            resultado['mensaje'] = (
                f'Registro soft-deleted id={submission_id}; se omite sin recrear'
            )
            return resultado
        try:
            datos_norm = _extraer_datos_normalizados(data)
            resumen_operativo = _aplicar_actualizaciones_operativas(
                registro=existente,
                payload=data,
                datos_norm=datos_norm,
                nombre_formulario=nombre_formulario,
            )
            existente.datos_recibidos = data
            existente.datos_procesados = _finalizar_datos_procesados(datos_norm, data, existente, resumen_operativo)
            existente.nombre_formulario = nombre_formulario
            existente.ruta_carpeta = ruta_context
            existente.fecha_procesamiento = timezone.now()
            existente.save(
                update_fields=[
                    'datos_recibidos',
                    'datos_procesados',
                    'nombre_formulario',
                    'ruta_carpeta',
                    'fecha_procesamiento',
                    'actualizo_cliente',
                    'actualizo_equipos',
                    'estado_revision',
                    'alerta_doble_trabajo',
                    'descripcion_alerta',
                ]
            )
            resultado['resultado'] = 'duplicado'
            resultado['alerta'] = bool(existente.alerta_doble_trabajo)
            resultado['mensaje'] = (
                existente.descripcion_alerta
                if existente.alerta_doble_trabajo and existente.descripcion_alerta
                else f'Ya existe registro con id={submission_id}'
            )
        except Exception as exc:
            logger.exception('Error webhook duplicado MoreApp id=%s', submission_id)
            resultado['resultado'] = 'duplicado'
            resultado['alerta'] = True
            resultado['mensaje'] = f'Ya existe id={submission_id}; error operativo: {exc}'
        return resultado

    datos_norm = _extraer_datos_normalizados(data)
    tiene_alerta, desc_alerta = _detectar_alerta_doble_trabajo(submission_id, datos_norm)

    estado = 'ALERTA_REVISION' if tiene_alerta else 'PROCESADO'
    registro = IntegracionMoreApp.objects.create(
        moreapp_submission_id=submission_id,
        nombre_formulario=nombre_formulario,
        ruta_carpeta=ruta_context,
        datos_recibidos=data,
        datos_procesados=datos_norm,
        estado_sincronizacion=estado,
        alerta_doble_trabajo=tiene_alerta,
        descripcion_alerta=desc_alerta,
        fecha_procesamiento=timezone.now(),
    )

    resumen_operativo = {}
    try:
        resumen_operativo = _aplicar_actualizaciones_operativas(
            registro=registro,
            payload=data,
            datos_norm=datos_norm,
            nombre_formulario=nombre_formulario,
        )
        registro.datos_procesados = _finalizar_datos_procesados(datos_norm, data, registro, resumen_operativo)
        registro.save(
            update_fields=[
                'datos_procesados',
                'actualizo_cliente',
                'actualizo_equipos',
                'estado_revision',
                'alerta_doble_trabajo',
                'descripcion_alerta',
            ]
        )
    except Exception as exc:
        logger.exception('Error operativo webhook MoreApp id=%s', submission_id)
        registro.alerta_doble_trabajo = True
        _asignar_estado_revision(registro, 'CON_ADVERTENCIA')
        detalle = f'ERROR_SYNC | {exc}'
        _append_descripcion_alerta(registro, detalle)
        try:
            registro.save(
                update_fields=[
                    'estado_revision',
                    'alerta_doble_trabajo',
                    'descripcion_alerta',
                ]
            )
        except Exception:
            logger.exception('No se pudo guardar alerta webhook id=%s', submission_id)

    resultado['resultado'] = 'nuevo'
    resultado['alerta'] = bool(registro.alerta_doble_trabajo or resumen_operativo.get('pendientes_revision'))
    if registro.descripcion_alerta:
        resultado['mensaje'] = registro.descripcion_alerta
    elif resumen_operativo.get('pendientes_revision'):
        resultado['mensaje'] = f'Pendientes operativos detectados: {len(resumen_operativo.get("pendientes_revision", []))}'
    else:
        resultado['mensaje'] = desc_alerta if tiene_alerta else 'OK'
    return resultado


def reprocesar_registro_moreapp(registro) -> Dict[str, Any]:
    """Reaplica actualizaciones de inventario/cliente sobre un registro MoreApp existente."""
    data = registro.datos_recibidos if isinstance(registro.datos_recibidos, dict) else {}
    if not data.get('data'):
        return {
            'success': False,
            'message': 'El registro no tiene payload JSON completo para reprocesar.',
        }

    nombre_formulario = registro.nombre_formulario or data.get('info', {}).get('formName', '')
    datos_norm = _extraer_datos_normalizados(data)

    registro.alerta_doble_trabajo = False
    registro.descripcion_alerta = ''
    registro.actualizo_cliente = False
    registro.actualizo_equipos = False

    from inventario.models import MovimientoInventario
    submission_tag = f'submission: {registro.moreapp_submission_id}'
    movimientos_antes = MovimientoInventario.objects.filter(
        origen_sistema='MOREAPP',
        observacion__icontains=submission_tag,
    ).count()

    resumen = _aplicar_actualizaciones_operativas(
        registro=registro,
        payload=data,
        datos_norm=datos_norm,
        nombre_formulario=nombre_formulario,
    )
    registro.datos_procesados = _finalizar_datos_procesados(datos_norm, data, registro, resumen)
    registro.fecha_procesamiento = timezone.now()
    if resumen.get('movimientos_generados', 0) > 0 or registro.actualizo_equipos:
        registro.estado_sincronizacion = 'PROCESADO'
    elif resumen.get('pendientes_revision') or registro.alerta_doble_trabajo:
        registro.estado_sincronizacion = 'ALERTA_REVISION'
    registro.save()

    movimientos_despues = MovimientoInventario.objects.filter(
        origen_sistema='MOREAPP',
        observacion__icontains=submission_tag,
    ).count()
    movimientos = max(0, movimientos_despues - movimientos_antes)
    pendientes = len(resumen.get('pendientes_revision', []))
    if movimientos:
        msg = f'Reprocesado: {movimientos} movimiento(s) nuevo(s) de inventario. Pendientes: {pendientes}.'
    else:
        msg = (
            'Sin movimientos nuevos: el inventario de este informe ya estaba aplicado. '
            f'Pendientes: {pendientes}.'
        )
    return {
        'success': movimientos > 0 or registro.actualizo_equipos or registro.actualizo_cliente,
        'message': msg,
        'resumen': resumen,
    }


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
