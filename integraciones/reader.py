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
from typing import Dict, Any, Tuple, Optional
import unicodedata

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

FORMULARIOS_SOPORTADOS = {
    'lectura': 'LECTURA',
    'mantenimiento telemetria v3': 'MANTENIMIENTO_TELEMETRIA_V3',
    'registro de medidores y telemetria v3': 'REGISTRO_MEDIDORES_TELEMETRIA_V3',
}


def _normalizar_texto(texto: Any) -> str:
    valor = str(texto or '').strip().lower().replace('_', ' ').replace('-', ' ')
    valor = unicodedata.normalize('NFKD', valor)
    valor = ''.join(c for c in valor if not unicodedata.combining(c))
    return ' '.join(valor.split())


def _as_text(valor: Any) -> str:
    """Convierte cualquier valor a texto seguro para evitar errores con .strip()."""
    if valor is None:
        return ''
    return str(valor).strip()


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
    return EstadoInventario.objects.filter(nombre__iexact=nombre_estado).first()


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
    responsable_override=None,
):
    from inventario.models import MovimientoInventario, MovimientoItem

    responsable = responsable_override or _obtener_responsable_sistema()
    if not responsable:
        return

    ubi_origen = getattr(equipo, 'ubicacion_actual', None)
    origen = ubi_origen or _obtener_o_crear_ubicacion('BODEGA_DELCO', 'Bodega Principal')

    estado_norm = _normalizar_texto(estado_nombre)
    if 'instal' in estado_norm:
        destino = _obtener_o_crear_ubicacion('CLIENTE', 'Instalado en cliente')
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
    )

    # Actualizar ubicacion_actual del equipo al destino (Punto 4)
    if hasattr(equipo, 'ubicacion_actual'):
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
    registro.alerta_doble_trabajo = True
    if registro.descripcion_alerta:
        registro.descripcion_alerta += f' | {detalle}'
    else:
        registro.descripcion_alerta = detalle
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

    # Regla 1: no instalar sin custodio previo ni ubicación válida.
    if _es_estado_instalado(estado_obj):
        if not _tiene_custodio_previo(equipo, tipo_equipo):
            _registrar_bloqueo_operativo(
                registro,
                tipo_equipo,
                identificador,
                'No se puede instalar sin custodio previo (entregado/en custodia).',
                contexto=observacion,
                registrar_pendiente=registrar_pendiente,
            )
            return False
        if not _ubicacion_valida_preinstalacion(equipo):
            _registrar_bloqueo_operativo(
                registro,
                tipo_equipo,
                identificador,
                'No se puede instalar desde una ubicación actual inválida o vacía.',
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
                                 registrar_pendiente=None, responsable_movimiento=None):
    cambios = []

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

    # Punto 1: validación previa de conflicto
    conflicto = _validar_conflicto_instalacion(equipo, tipo_equipo, cliente_obj)
    if conflicto:
        _registrar_bloqueo_operativo(
            registro,
            tipo_equipo,
            _identificador_equipo(equipo, tipo_equipo),
            conflicto,
            contexto=observacion,
            registrar_pendiente=registrar_pendiente,
        )
        return False

    if estado_obj and getattr(equipo, 'estado_inventario_id', None) != estado_obj.id:
        equipo.estado_inventario = estado_obj
        cambios.append('estado_inventario')

    if cliente_obj and hasattr(equipo, 'cliente_id') and equipo.cliente_id != cliente_obj.id:
        equipo.cliente = cliente_obj
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

    if tipo_equipo == 'MEDIDOR' and cliente_obj and cliente_obj.medidor_actual_id != equipo.id:
        cliente_obj.medidor_actual = equipo
        cliente_obj.save(update_fields=['medidor_actual'])

    if cambios:
        equipo.save(update_fields=cambios)
        # Puntos 5 y 10: tipo MOREAPP, origen_sistema MOREAPP
        _registrar_movimiento_equipo(
            equipo,
            tipo_equipo,
            observacion,
            estado_obj.nombre if estado_obj else '',
            origen_sistema='MOREAPP',
            tipo_override='MOREAPP',
            responsable_override=responsable_movimiento,
        )
        registro.actualizo_equipos = True
        return True
    return False


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

    medidor_serie = _as_text(datos_norm.get('serial_number') or _valor_campo_fuentes(
        fuentes,
        ['medidor', 'serie medidor', 'n serie medidor', 'numero medidor', 'serie', 'medidorsc4i'],
    ) or '')
    medidor_activo_serie = _as_text(datos_norm.get('medidor_activo_numero'))
    medidor_dejado_serie = _as_text(datos_norm.get('medidor_dejado_numero'))
    modem_encontrado_serie = _as_text(datos_norm.get('modem_encontrado'))
    modem_dejado_serie = _as_text(datos_norm.get('modem_dejado') or datos_norm.get('modem_numero'))
    modem_serie = modem_dejado_serie or modem_encontrado_serie or _as_text(_valor_campo_fuentes(fuentes, ['serie modem', 'modem serie', 'numero modem']))
    sim_ip = _as_text(datos_norm.get('ip_dejada') or _valor_campo_fuentes(fuentes, ['ip dejada', 'ip', 'direccion ip']))
    puerto_dejado = _as_text(datos_norm.get('puerto_dejado') or _valor_campo_fuentes(fuentes, ['puerto dejado', 'puerto']))

    cliente_obj = None
    if cliente_codigo:
        cliente_obj = Cliente.objects.filter(numero_cliente__iexact=cliente_codigo).first()
        if not cliente_obj:
            cliente_obj = Cliente.objects.filter(numero_cliente__icontains=cliente_codigo).first()

    resumen = {
        'formulario_canonico': formulario_canonico,
        'cliente_encontrado': bool(cliente_obj),
        'medidor_encontrado': False,
        'modem_encontrado': False,
        'sim_encontrada': False,
        'estado_aplicado': estado_obj.nombre if estado_obj else '',
        'movimientos_generados': 0,
        'pendientes_revision': [],
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
        ident = _as_text(identificador)
        if not ident:
            return
        resumen['pendientes_revision'].append({
            'tipo_equipo': tipo_equipo,
            'identificador': ident,
            'motivo': motivo,
        })

    if cliente_obj:
        cambios_cliente = []
        direccion = _as_text(datos_norm.get('cliente_direccion', ''))
        comuna = _as_text(datos_norm.get('cliente_comuna', ''))
        if direccion and cliente_obj.direccion != direccion:
            cliente_obj.direccion = direccion
            cambios_cliente.append('direccion')
        if comuna and cliente_obj.comuna != comuna:
            cliente_obj.comuna = comuna
            cambios_cliente.append('comuna')
        if not cliente_obj.activo:
            cliente_obj.activo = True
            cambios_cliente.append('activo')
        if cambios_cliente:
            cliente_obj.save(update_fields=cambios_cliente)
            registro.actualizo_cliente = True

    def _buscar_medidor(serie):
        if not serie:
            return None
        return Medidor.objects.filter(serie__iexact=serie).first()

    def _buscar_modem_por_serie(serie):
        if not serie:
            return None
        return Modem.objects.filter(serie__iexact=serie).first()

    def _buscar_sim_por_ip(ip):
        if not ip:
            return None
        sim = SimCard.objects.filter(direccion_ip__iexact=ip).first()
        if sim:
            return sim
        return SimCard.objects.filter(ip_fija__iexact=ip).first()

    observacion_base = (
        f'Actualización MoreApp ({formulario_canonico}) '
        f'| submission: {registro.moreapp_submission_id}'
    )
    tecnico_moreapp = _as_text(datos_norm.get('tecnico_responsable'))
    responsable_movimiento = _resolver_responsable_moreapp(tecnico_moreapp) or _obtener_responsable_sistema()
    medidor_principal = _buscar_medidor(medidor_serie)

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

        medidor_instalado = _buscar_medidor(medidor_dejado_serie)
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
        elif medidor_dejado_serie:
            _agregar_pendiente('MEDIDOR', medidor_dejado_serie, 'Serie de medidor dejado no encontrada en inventario')

        modem_instalado = _buscar_modem_por_serie(modem_dejado_serie)
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
        elif modem_dejado_serie:
            _agregar_pendiente('MODEM', modem_dejado_serie, 'Serie de módem dejado no encontrada en inventario')

        sim_instalada = _buscar_sim_por_ip(sim_ip)
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
        elif sim_ip:
            _agregar_pendiente('SIM', sim_ip, 'IP dejada de SIM no encontrada en inventario')

        # Punto 8: estado_revision para el bloque REG_MEDIDORES
        if resumen['pendientes_revision'] or registro.alerta_doble_trabajo:
            registro.estado_revision = 'CON_ADVERTENCIA'
        else:
            registro.estado_revision = 'REVISADO'
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
        _agregar_pendiente('MEDIDOR', medidor_serie, 'Serie de medidor no encontrada en inventario')

    modem_encontrado = None
    if formulario_canonico == 'MANTENIMIENTO_TELEMETRIA_V3' and modem_encontrado_serie and modem_dejado_serie:
        modem_retirado = _buscar_modem_por_serie(modem_encontrado_serie)
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
        modem_encontrado = _buscar_modem_por_serie(modem_serie)
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
    elif modem_serie:
        _agregar_pendiente('MODEM', modem_serie, 'Serie de módem no encontrada en inventario')

    sim = _buscar_sim_por_ip(sim_ip)
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
    elif sim_ip:
        _agregar_pendiente('SIM', sim_ip, 'IP de SIM no encontrada en inventario')

    # Punto 8: establecer estado_revision según resultados
    if resumen['pendientes_revision']:
        registro.estado_revision = 'CON_ADVERTENCIA'
    elif registro.alerta_doble_trabajo:
        registro.estado_revision = 'CON_ADVERTENCIA'
    else:
        registro.estado_revision = 'REVISADO'

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
        cliente_c = _as_text(datos_c.get('cliente_codigo', ''))
        trabajo_c = (_as_text(datos_c.get('trabajo', ''))
                 or _as_text(datos_c.get('actividad', '')))

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


def leer_carpetas(base_dir: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
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
                   numero_correlativo: Optional[int], dry_run: bool) -> Dict[str, Any]:
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
        datos_norm = _extraer_datos_normalizados(data)
        resumen_operativo = _aplicar_actualizaciones_operativas(
            registro=existente,
            payload=data,
            datos_norm=datos_norm,
            nombre_formulario=nombre_formulario,
        )
        existente.datos_recibidos = data
        existente.datos_procesados = {**datos_norm, 'resultado_operativo': resumen_operativo}
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
        logger.info('Duplicado omitido: %s', submission_id)
        return resultado

    # --- Extraer datos normalizados ---
    datos_norm = _extraer_datos_normalizados(data)

    # --- Detección alerta doble trabajo ---
    tiene_alerta, desc_alerta = _detectar_alerta_doble_trabajo(submission_id, datos_norm)

    # --- Guardar en BD ---
    with transaction.atomic():
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

        # Aplicar actualización operativa (cliente/equipos) según formulario y payload
        resumen_operativo = _aplicar_actualizaciones_operativas(
            registro=registro,
            payload=data,
            datos_norm=datos_norm,
            nombre_formulario=nombre_formulario,
        )
        registro.datos_procesados = {**datos_norm, 'resultado_operativo': resumen_operativo}
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
        datos_norm = _extraer_datos_normalizados(data)
        resumen_operativo = _aplicar_actualizaciones_operativas(
            registro=existente,
            payload=data,
            datos_norm=datos_norm,
            nombre_formulario=nombre_formulario,
        )
        existente.datos_recibidos = data
        existente.datos_procesados = {**datos_norm, 'resultado_operativo': resumen_operativo}
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
        return resultado

    datos_norm = _extraer_datos_normalizados(data)
    tiene_alerta, desc_alerta = _detectar_alerta_doble_trabajo(submission_id, datos_norm)

    with transaction.atomic():
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

        resumen_operativo = _aplicar_actualizaciones_operativas(
            registro=registro,
            payload=data,
            datos_norm=datos_norm,
            nombre_formulario=nombre_formulario,
        )
        registro.datos_procesados = {**datos_norm, 'resultado_operativo': resumen_operativo}
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

    resultado['resultado'] = 'nuevo'
    resultado['alerta'] = bool(registro.alerta_doble_trabajo or resumen_operativo.get('pendientes_revision'))
    if registro.descripcion_alerta:
        resultado['mensaje'] = registro.descripcion_alerta
    elif resumen_operativo.get('pendientes_revision'):
        resultado['mensaje'] = f'Pendientes operativos detectados: {len(resumen_operativo.get("pendientes_revision", []))}'
    else:
        resultado['mensaje'] = desc_alerta if tiene_alerta else 'OK'
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
