"""Etiquetas legibles para auditoría / trazabilidad."""

from __future__ import annotations

ACCION_LABELS = {
    'MOREAPP_REVISION_UPDATE': 'MoreApp — Actualización de revisión',
    'INVENTORY_UPDATE': 'Inventario — Actualización',
    'CLIENT_CREATE': 'Cliente — Creación',
    'CLIENT_CREATE_FIELD': 'Cliente — Alta de campos',
    'CLIENT_UPDATE': 'Cliente — Actualización',
    'CLIENT_IMPORT': 'Cliente — Importación',
    'CLIENT_SOFT_DELETE': 'Cliente — Eliminación',
    'OT_CREATE': 'Orden de trabajo — Creación',
    'OT_STATE_CHANGE': 'Orden de trabajo — Cambio de estado',
    'OT_REASSIGN_TECH': 'Orden de trabajo — Reasignación de técnico',
    'CARGA_CREATE': 'Carga administrativa — Creación',
    'CARGA_ASSIGN': 'Carga administrativa — Asignación',
    'CARGA_COMPLETE': 'Carga administrativa — Completada',
    'CARGA_CANCEL': 'Carga administrativa — Cancelación',
    'CARGA_DELETE': 'Carga administrativa — Eliminación',
    'CARGA_UPDATE': 'Carga administrativa — Actualización',
    'SOFT_DELETE': 'Eliminación lógica',
    'TEST_AUDIT': 'Prueba de auditoría',
}

ENTIDAD_LABELS = {
    'Cliente': 'Cliente',
    'OrdenTrabajo': 'Orden de trabajo',
    'CargaAdministrativa': 'Orden de trabajo administrativa',
    'AdjuntoCarga': 'Adjunto de carga administrativa',
    'IntegracionMoreApp': 'MoreApp',
    'Medidor': 'Medidor',
    'SimCard': 'SIM Card',
    'Modem': 'Módem',
    'MovimientoInventario': 'Movimiento de inventario',
    'Usuario': 'Usuario',
}

CAMPO_LABELS = {
    'estado_revision': 'Estado de revisión',
    'estado': 'Estado',
    'numero_cliente': 'Nº cliente',
    'customer_name': 'Nombre cliente',
    'installation_address': 'Dirección instalación',
    'meter_serial_n_1': 'Serie medidor',
    'meter_manufacturer_id': 'Marca medidor',
    'tipo_suministro': 'Tipo de suministro',
    'fecha_entrega': 'Fecha de entrega',
    'estado_inventario_id': 'Estado inventario',
    'entregado_a_id': 'Entregado a',
    'cliente_id': 'Cliente',
    'tecnico_responsable_id': 'Técnico responsable',
    'activo': 'Activo',
    'proyecto': 'Proyecto',
    'comuna': 'Comuna',
    'sector': 'Sector',
    'ip': 'IP',
    'puerto': 'Puerto',
    'modem': 'Módem',
    'estado_sci4': 'Estado SCi4',
    'estado_stb': 'Estado STB',
    'medidor_actual_id': 'Medidor actual',
}

# Códigos típicos en valor anterior / valor nuevo
VALOR_LABELS = {
    # Revisión MoreApp
    'PENDIENTE': 'Pendiente de revisión',
    'CON_ADVERTENCIA': 'Con advertencia',
    'REVISADO': 'Revisado OK',
    'DESCARTADO': 'Descartado',
    'CRITICA': 'Crítica',
    # Sync MoreApp
    'PROCESANDO': 'Procesando',
    'PROCESADO': 'Procesado',
    'EXITOSO': 'Exitoso',
    'ERROR': 'Error',
    'ERROR_JSON': 'Error — JSON inválido',
    'ERROR_LECTURA': 'Error — Lectura',
    'DUPLICADO': 'Duplicado',
    'ALERTA_REVISION': 'Alerta — Revisión requerida',
    # Estados OT
    'CREADA': 'Creada',
    'ASIGNADA': 'Asignada',
    'EN_EJECUCION': 'En ejecución',
    'REASIGNADA': 'Reasignada',
    'MANTENIMIENTO': 'Mantenimiento',
    'REALIZADA': 'Realizada',
    'REALIZADA_PENDIENTE_COMPROBACION': 'Realizada — Pendiente comprobación',
    'PENDIENTE_VALIDACION': 'Pendiente validación',
    'VALIDADA': 'Validada',
    'OBSERVADA': 'Observada',
    'FINALIZADA': 'Finalizada',
    'CANCELADA': 'Cancelada',
    # Tipos de trabajo
    'INSTALACION': 'Instalación',
    'CAMBIO': 'Cambio de equipo',
    'RETIRO': 'Retiro',
    'MANTENCION': 'Mantención',
    'REPARACION': 'Reparación',
    'INSPECCION': 'Inspección',
    'CONFIGURACION': 'Configuración',
    'OTRO': 'Otro',
    # Inventario / flags
    'DISPONIBLE': 'Disponible',
    'ASIGNADO': 'Asignado',
    'INSTALADO': 'Instalado',
    'RETIRADO': 'Retirado',
    'ACTIVO': 'Activo',
    'INACTIVO': 'Inactivo',
    'True': 'Sí',
    'False': 'No',
    'true': 'Sí',
    'false': 'No',
    'None': '—',
    'null': '—',
}


def _capitalizar_frase(texto: str) -> str:
    """Primera letra en mayúscula; conserva el resto."""
    valor = str(texto or '').strip()
    if not valor:
        return '—'
    return valor[0].upper() + valor[1:]


def _titulo_desde_codigo(codigo: str) -> str:
    texto = str(codigo or '').strip().replace('_', ' ').replace('-', ' ')
    if not texto:
        return '—'
    partes = []
    for p in texto.split():
        upper = p.upper()
        if upper in {'OT', 'IP', 'SIM', 'STB', 'PDF', 'ID', 'MOREAPP'}:
            partes.append('MoreApp' if upper == 'MOREAPP' else upper)
        else:
            partes.append(p.capitalize())
    return ' '.join(partes)


def label_accion(codigo: str) -> str:
    key = str(codigo or '').strip()
    if key in ACCION_LABELS:
        return ACCION_LABELS[key]
    return _capitalizar_frase(_titulo_desde_codigo(key))


def label_entidad(codigo: str) -> str:
    key = str(codigo or '').strip()
    if key in ENTIDAD_LABELS:
        return ENTIDAD_LABELS[key]
    return _capitalizar_frase(_titulo_desde_codigo(key))


def label_campo(codigo: str) -> str:
    key = str(codigo or '').strip()
    if not key:
        return '—'
    if key in CAMPO_LABELS:
        return CAMPO_LABELS[key]
    return _capitalizar_frase(_titulo_desde_codigo(key))


def label_valor(codigo: str) -> str:
    """Valor anterior/nuevo de auditoría en texto legible."""
    if codigo is None:
        return '—'
    key = str(codigo).strip()
    if not key:
        return '—'
    if key in VALOR_LABELS:
        return VALOR_LABELS[key]
    # Códigos en MAYÚSCULAS_CON_GUION → frase legible
    if key.isupper() and ('_' in key or key.isalpha()):
        return _capitalizar_frase(_titulo_desde_codigo(key))
    return key
