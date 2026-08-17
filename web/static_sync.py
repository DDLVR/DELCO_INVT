"""Copia CSS fuente a STATIC_ROOT para WhiteNoise en Hostingplus.

Tras ``git pull``, el HTML nuevo llega de inmediato, pero WhiteNoise sirve
``staticfiles/``. Si no se corre collectstatic, el modal de import y otros
estilos quedan desfasados (input nativo «Elegir archivo», radios sin tarjetas).

Esta copia cubre el CSS de la app en cada arranque de Passenger y elimina
``.gz``/``.br`` viejos para que WhiteNoise no siga sirviendo el comprimido
anterior.
"""
from __future__ import annotations

import shutil
from pathlib import Path


def sincronizar_css_fuente_a_staticfiles(base_dir: Path | str) -> int:
    """Copia ``static/css/*.css`` hacia ``staticfiles/css/``. Devuelve copiados."""
    base = Path(base_dir)
    src_dir = base / "static" / "css"
    dest_dir = base / "staticfiles" / "css"
    if not src_dir.is_dir():
        return 0
    dest_dir.mkdir(parents=True, exist_ok=True)
    copiados = 0
    for src in sorted(src_dir.glob("*.css")):
        if not src.is_file():
            continue
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        for extra in (dest.with_name(dest.name + ".gz"), dest.with_name(dest.name + ".br")):
            if extra.is_file():
                extra.unlink()
        copiados += 1
    return copiados
