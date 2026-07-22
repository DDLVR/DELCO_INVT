"""Extracción de GPS y fotos desde submissions MoreApp (punto 6 PDF)."""

from __future__ import annotations

import logging
import os
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.files import File

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
FOTO_KEY_HINTS = (
    'foto', 'photo', 'image', 'imagen', 'panoram', 'panorm', 'caratula',
    'gabinete', 'sello', 'antena', 'empalme', 'evidencia',
)
GRIDFS_RE = re.compile(r'^gridfs://[^/]+/([0-9a-fA-F-]{16,})$')


def _as_text(value: Any) -> str:
    if value is None:
        return ''
    return str(value).strip()


def _label_from_key(campo: str) -> str:
    texto = re.sub(r'([a-z])([A-Z])', r'\1 \2', campo or '')
    texto = texto.replace('_', ' ').replace('-', ' ')
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto[:1].upper() + texto[1:] if texto else 'Foto'


def extraer_geo_desde_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza el widget location de MoreApp a lat/lng + dirección."""
    data = payload.get('data') if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}
    location = data.get('location')
    if not isinstance(location, dict):
        return {}

    coords = location.get('coordinates') if isinstance(location.get('coordinates'), dict) else {}
    lat = coords.get('latitude', location.get('latitude'))
    lng = coords.get('longitude', location.get('longitude'))
    try:
        lat_f = float(lat) if lat is not None and str(lat).strip() != '' else None
    except (TypeError, ValueError):
        lat_f = None
    try:
        lng_f = float(lng) if lng is not None and str(lng).strip() != '' else None
    except (TypeError, ValueError):
        lng_f = None

    formatted = _as_text(location.get('formattedValue') or location.get('address'))
    loc_detail = location.get('location') if isinstance(location.get('location'), dict) else {}
    if not formatted and loc_detail:
        parts = [
            _as_text(loc_detail.get('road')),
            _as_text(loc_detail.get('postcode')),
            _as_text(loc_detail.get('city')),
            _as_text(loc_detail.get('country')),
        ]
        formatted = ', '.join(p for p in parts if p)

    if lat_f is None and lng_f is None and not formatted:
        return {}

    maps_url = ''
    if lat_f is not None and lng_f is not None:
        maps_url = f'https://www.google.com/maps?q={lat_f},{lng_f}'

    return {
        'latitude': lat_f,
        'longitude': lng_f,
        'formatted': formatted,
        'maps_url': maps_url,
    }


def _es_campo_foto(nombre: str) -> bool:
    low = (nombre or '').lower()
    return any(h in low for h in FOTO_KEY_HINTS)


def _parse_foto_valor(campo: str, valor: Any) -> Optional[Dict[str, Any]]:
    if valor is None or valor == '':
        return None

    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None
        m = GRIDFS_RE.match(texto)
        if m or texto.lower().startswith('gridfs://'):
            return {
                'campo': campo,
                'label': _label_from_key(campo),
                'gridfs_ref': texto,
                'gridfs_id': m.group(1) if m else '',
                'url': '',
                'nombre_archivo': '',
                'ruta_local': '',
                'media_url': '',
                'disponible': False,
            }
        if texto.lower().startswith('http://') or texto.lower().startswith('https://'):
            return {
                'campo': campo,
                'label': _label_from_key(campo),
                'gridfs_ref': '',
                'gridfs_id': '',
                'url': texto,
                'nombre_archivo': os.path.basename(texto.split('?')[0]) or f'{campo}.jpg',
                'ruta_local': '',
                'media_url': '',
                'disponible': True,
            }
        return None

    if isinstance(valor, dict):
        # Widget archivo/foto tipico MoreApp
        nombre = _as_text(valor.get('name') or valor.get('fileName') or valor.get('filename'))
        mime = _as_text(valor.get('mimeType') or valor.get('contentType')).lower()
        url = _as_text(valor.get('url') or valor.get('downloadUrl') or valor.get('href'))
        gridfs = _as_text(valor.get('gridfs') or valor.get('id') or valor.get('fileId'))
        if gridfs and not gridfs.lower().startswith('gridfs://'):
            # a veces solo viene el uuid
            if re.match(r'^[0-9a-fA-F-]{16,}$', gridfs):
                gridfs = f'gridfs://registrationFiles/{gridfs}'
        raw = gridfs or url or _as_text(valor.get('formattedValue'))
        if not raw and not nombre:
            return None
        if mime and not mime.startswith('image/') and not _es_campo_foto(campo):
            return None
        item = _parse_foto_valor(campo, raw) if raw else {
            'campo': campo,
            'label': _label_from_key(campo),
            'gridfs_ref': '',
            'gridfs_id': '',
            'url': url,
            'nombre_archivo': nombre,
            'ruta_local': '',
            'media_url': '',
            'disponible': bool(url),
        }
        if nombre:
            item['nombre_archivo'] = nombre
        return item

    if isinstance(valor, list):
        # Se maneja en el walker (varios items)
        return None

    return None


def extraer_fotos_desde_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Recorre data.* y arma lista de evidencias fotográficas referenciadas."""
    data = payload.get('data') if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return []

    fotos: List[Dict[str, Any]] = []
    vistos = set()

    def _agregar(item: Optional[Dict[str, Any]]):
        if not item:
            return
        key = (
            item.get('gridfs_ref')
            or item.get('url')
            or item.get('nombre_archivo')
            or item.get('campo')
        )
        if not key or key in vistos:
            return
        vistos.add(key)
        fotos.append(item)

    def walk(obj: Any, path: str = ''):
        if isinstance(obj, dict):
            for k, v in obj.items():
                hoja = f'{path}.{k}' if path else k
                if isinstance(v, list):
                    if _es_campo_foto(k):
                        for idx, entry in enumerate(v):
                            _agregar(_parse_foto_valor(f'{k}_{idx+1}', entry))
                    else:
                        walk(v, hoja)
                elif isinstance(v, dict):
                    if _es_campo_foto(k):
                        _agregar(_parse_foto_valor(k, v))
                    else:
                        walk(v, hoja)
                else:
                    if _es_campo_foto(k):
                        _agregar(_parse_foto_valor(k, v))
        elif isinstance(obj, list):
            for i, entry in enumerate(obj):
                walk(entry, f'{path}[{i}]')

    walk(data)
    return fotos


def _listar_imagenes_carpeta(ruta_carpeta: str) -> List[str]:
    if not ruta_carpeta or not os.path.isdir(ruta_carpeta):
        return []
    archivos = []
    try:
        for name in os.listdir(ruta_carpeta):
            path = os.path.join(ruta_carpeta, name)
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                archivos.append(path)
    except OSError:
        logger.exception('No se pudo listar imágenes en %s', ruta_carpeta)
    return sorted(archivos)


def _media_subdir(submission_id: str) -> str:
    safe = re.sub(r'[^a-zA-Z0-9_-]+', '_', submission_id or 'sin_id')[:80]
    return os.path.join('moreapp_fotos', safe)


def _copiar_a_media(src_path: str, submission_id: str) -> Tuple[str, str]:
    """Copia imagen a MEDIA_ROOT/moreapp_fotos/<submission>/ y retorna (relpath, media_url)."""
    rel_dir = _media_subdir(submission_id)
    dest_dir = os.path.join(str(settings.MEDIA_ROOT), rel_dir)
    os.makedirs(dest_dir, exist_ok=True)
    nombre = os.path.basename(src_path)
    dest_path = os.path.join(dest_dir, nombre)
    if not os.path.exists(dest_path):
        shutil.copy2(src_path, dest_path)
    rel = f'{rel_dir.replace(os.sep, "/")}/{nombre}'
    media_url = f'{settings.MEDIA_URL.rstrip("/")}/{rel}'
    return rel, media_url


def asociar_archivos_locales(
    fotos: List[Dict[str, Any]],
    ruta_carpeta: str,
    submission_id: str,
) -> List[Dict[str, Any]]:
    """Empareja refs gridfs/nombre con archivos locales de la carpeta MoreApp."""
    locales = _listar_imagenes_carpeta(ruta_carpeta)
    if not locales and not fotos:
        return fotos

    usados = set()

    def _tomar_por_uuid(uuid_val: str) -> Optional[str]:
        if not uuid_val:
            return None
        for path in locales:
            if uuid_val.lower() in os.path.basename(path).lower() and path not in usados:
                return path
        return None

    for foto in fotos:
        path = None
        if foto.get('gridfs_id'):
            path = _tomar_por_uuid(foto['gridfs_id'])
        if not path and foto.get('nombre_archivo'):
            candidato = os.path.join(ruta_carpeta, foto['nombre_archivo'])
            if os.path.isfile(candidato):
                path = candidato
        if path:
            usados.add(path)
            rel, url = _copiar_a_media(path, submission_id)
            foto['ruta_local'] = rel
            foto['media_url'] = url
            foto['nombre_archivo'] = foto.get('nombre_archivo') or os.path.basename(path)
            foto['disponible'] = True

    # Archivos locales sin match: agregar como fotos adicionales
    for path in locales:
        if path in usados:
            continue
        rel, url = _copiar_a_media(path, submission_id)
        nombre = os.path.basename(path)
        fotos.append({
            'campo': 'archivo_local',
            'label': f'Evidencia {nombre}',
            'gridfs_ref': '',
            'gridfs_id': '',
            'url': '',
            'nombre_archivo': nombre,
            'ruta_local': rel,
            'media_url': url,
            'disponible': True,
        })
    return fotos


def enriquecer_datos_media(
    datos_norm: Dict[str, Any],
    payload: Dict[str, Any],
    ruta_carpeta: str = '',
    submission_id: str = '',
) -> Dict[str, Any]:
    """Agrega geo + fotos a datos_procesados."""
    out = dict(datos_norm or {})
    geo = extraer_geo_desde_payload(payload or {})
    if geo:
        out['geo'] = geo
        if geo.get('formatted') and not out.get('location'):
            out['location'] = geo['formatted']

    fotos = extraer_fotos_desde_payload(payload or {})
    fotos = asociar_archivos_locales(fotos, ruta_carpeta or '', submission_id or '')
    out['fotos'] = fotos
    out['fotos_disponibles'] = sum(1 for f in fotos if f.get('disponible'))
    out['fotos_total'] = len(fotos)
    return out


def crear_adjuntos_orden_desde_fotos(orden, registro, usuario=None) -> int:
    """Crea AdjuntoOrden para fotos disponibles aún no vinculadas a la OT."""
    if not orden or not registro:
        return 0

    from ordenes_trabajo.models import AdjuntoOrden

    datos = registro.datos_procesados if isinstance(registro.datos_procesados, dict) else {}
    fotos = datos.get('fotos') or []
    if not fotos:
        return 0

    creados = 0
    for foto in fotos:
        if not foto.get('disponible'):
            continue
        nombre = foto.get('nombre_archivo') or f"{foto.get('campo') or 'foto'}.jpg"
        meta_key = foto.get('gridfs_ref') or foto.get('ruta_local') or foto.get('url') or nombre
        ya = orden.adjuntos.filter(
            tipo='FOTO',
            metadata__moreapp_key=meta_key,
        ).exists()
        if ya:
            continue

        adj = AdjuntoOrden(
            orden=orden,
            tipo='FOTO',
            nombre_archivo=nombre,
            subido_por=usuario,
            url_externa=(foto.get('url') or '')[:200],
            metadata={
                'source': 'MoreApp',
                'submission_id': registro.moreapp_submission_id,
                'campo': foto.get('campo'),
                'label': foto.get('label'),
                'moreapp_key': meta_key,
                'gridfs_ref': foto.get('gridfs_ref') or '',
            },
        )

        rel = foto.get('ruta_local') or ''
        abs_path = os.path.join(str(settings.MEDIA_ROOT), rel.replace('/', os.sep)) if rel else ''
        if abs_path and os.path.isfile(abs_path):
            # FileField de AdjuntoOrden es obligatorio: guardar copia vía storage
            with open(abs_path, 'rb') as fh:
                adj.archivo.save(nombre, File(fh), save=False)
            adj.save()
            creados += 1
        elif foto.get('url'):
            adj.save()
            creados += 1
        elif foto.get('gridfs_ref'):
            # Referencia MoreApp sin archivo local: queda documentada en la OT
            adj.url_externa = ''
            adj.metadata['pendiente_archivo'] = True
            adj.save()
            creados += 1

    if creados:
        registro.creo_adjuntos = True
        registro.save(update_fields=['creo_adjuntos'])
    return creados
