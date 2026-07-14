"""Compatibilidad SQLite para desarrollo local con Python 3.8.

La build oficial de SQLite en Windows (p.ej. 3.35) a menudo no incluye
JSON1. Django 4.2 exige JSON() para marcar supports_json_field y usa
JSON_VALID / JSON_TYPE / JSON_EXTRACT en JSONField.

Registramos equivalentes en Python. Solo aplica a sqlite; MySQL no cambia.
"""
import json
import re

from django.db.backends.signals import connection_created

_MISSING = object()
_PATH_DOT = re.compile(r'\.("(?:\\.|[^"])*"|[A-Za-z_][\w]*)|\[(\d+)\]')


def _as_text(value):
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return value.decode('utf-8')
    return value if isinstance(value, str) else str(value)


def _parse_json(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(_as_text(value))


def _path_parts(path):
    if path is None or path == '' or path == '$':
        return []
    text = str(path)
    if not text.startswith('$'):
        return []
    parts = []
    for match in _PATH_DOT.finditer(text[1:]):
        quoted_or_ident, index = match.groups()
        if index is not None:
            parts.append(int(index))
            continue
        token = quoted_or_ident
        if token.startswith('"') and token.endswith('"'):
            parts.append(json.loads(token))
        else:
            parts.append(token)
    return parts


def _resolve(data, path='$'):
    current = data
    for part in _path_parts(path):
        if current is None:
            return _MISSING
        if isinstance(part, int):
            if not isinstance(current, list) or part < 0 or part >= len(current):
                return _MISSING
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                return _MISSING
            current = current[part]
    return current


def _json(value):
    """Equivalente a SQLite json(X): valida y minifica."""
    if value is None:
        return None
    data = _parse_json(value)
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


def _json_valid(value):
    if value is None:
        return None
    try:
        _parse_json(value)
        return 1
    except (TypeError, ValueError, UnicodeDecodeError):
        return 0


def _sqlite_json_type_name(resolved):
    if resolved is None:
        return 'null'
    if isinstance(resolved, bool):
        return 'true' if resolved else 'false'
    if isinstance(resolved, int):
        return 'integer'
    if isinstance(resolved, float):
        return 'real'
    if isinstance(resolved, str):
        return 'text'
    if isinstance(resolved, list):
        return 'array'
    if isinstance(resolved, dict):
        return 'object'
    return 'text'


def _json_type(value, path='$'):
    try:
        data = _parse_json(value)
    except (TypeError, ValueError, UnicodeDecodeError):
        return None
    resolved = _resolve(data, path if path is not None else '$')
    if resolved is _MISSING:
        return None
    return _sqlite_json_type_name(resolved)


def _json_extract(value, path='$'):
    try:
        data = _parse_json(value)
    except (TypeError, ValueError, UnicodeDecodeError):
        return None
    resolved = _resolve(data, path if path is not None else '$')
    if resolved is _MISSING:
        return None
    if resolved is None:
        return None
    if isinstance(resolved, bool):
        return 1 if resolved else 0
    if isinstance(resolved, (dict, list)):
        return json.dumps(resolved, ensure_ascii=False, separators=(',', ':'))
    return resolved


def _json_quote(value):
    if value is None:
        return 'null'
    return json.dumps(value, ensure_ascii=False)


def _json_array(*args):
    return json.dumps(list(args), ensure_ascii=False, separators=(',', ':'))


def _json_object(*args):
    if len(args) % 2 != 0:
        raise ValueError('JSON_OBJECT requiere cantidad par de argumentos')
    data = {}
    for i in range(0, len(args), 2):
        data[str(args[i])] = args[i + 1]
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


def _create_function(connection, name, arity, callback):
    create = connection.connection.create_function
    try:
        create(name, arity, callback, deterministic=True)
    except TypeError:
        create(name, arity, callback)


def _mark_json_supported(connection):
    """Django cachea supports_json_field con un probe a JSON(); lo forzamos."""
    features = connection.features
    features.__dict__['supports_json_field'] = True


def _register_sqlite_json_functions(sender, connection, **kwargs):
    if connection.vendor != 'sqlite':
        return
    _create_function(connection, 'JSON', 1, _json)
    _create_function(connection, 'JSON_VALID', 1, _json_valid)
    _create_function(connection, 'JSON_TYPE', 1, lambda value: _json_type(value, '$'))
    _create_function(connection, 'JSON_TYPE', 2, _json_type)
    _create_function(connection, 'JSON_EXTRACT', 2, _json_extract)
    _create_function(connection, 'JSON_QUOTE', 1, _json_quote)
    # Aridad variable: -1 = cualquier cantidad (SQLite/Python).
    _create_function(connection, 'JSON_ARRAY', -1, _json_array)
    _create_function(connection, 'JSON_OBJECT', -1, _json_object)
    _mark_json_supported(connection)


def enable_sqlite_json_valid():
    """Nombre histórico: registra todas las funciones JSON necesarias."""
    connection_created.connect(_register_sqlite_json_functions)
    try:
        from django.db import connection

        if connection.connection is not None and connection.vendor == 'sqlite':
            _register_sqlite_json_functions(None, connection)
    except Exception:
        pass
