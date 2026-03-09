#!/usr/bin/env python
"""
Script de preparación para despliegue: limpia archivos temporales y empaqueta en ZIP.
Ejecutar desde el directorio `Backend/` antes de subir a cPanel.
"""
import os
import sys
import shutil
from pathlib import Path


def remove_patterns(base_dir: Path, patterns):
    for pattern in patterns:
        for path in base_dir.rglob(pattern):
            try:
                if path.is_file():
                    path.unlink()
                    print(f"Eliminado archivo: {path}")
                elif path.is_dir():
                    shutil.rmtree(path)
                    print(f"Eliminado directorio: {path}")
            except Exception as e:
                print(f"Error al eliminar {path}: {e}")


def ensure_gitignore(base_dir: Path):
    gitignore_path = base_dir / ".gitignore"
    default_entries = [
        "# Archivos locales y temporales",
        ".env",
        "db.sqlite3",
        "__pycache__/",
        "*.pyc",
        "*.log",
        "build/",
        "dist/",
        "*.egg-info/",
        "staticfiles/",
        "*.zip",
    ]
    if gitignore_path.exists():
        print(".gitignore ya existe, verificando entradas...")
        existing = gitignore_path.read_text().splitlines()
        with gitignore_path.open("a", encoding="utf-8") as f:
            for entry in default_entries:
                if entry not in existing:
                    f.write(entry + "\n")
                    print(f"Añadido a .gitignore: {entry}")
    else:
        print("Creando .gitignore con entradas básicas...")
        gitignore_path.write_text("\n".join(default_entries) + "\n")


def make_zip(base_dir: Path, zip_name: str):
    # Antes de empaquetar, ignoramos explícitamente los archivos de salida
    zip_path = base_dir / zip_name
    if zip_path.exists():
        zip_path.unlink()
    print(f"Creando archivo ZIP: {zip_path}")
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=base_dir)
    print("ZIP generado correctamente.")


def make_tar(base_dir: Path, tar_name: str):
    # Igual que ZIP: no empaquetar el tar existente
    tar_path = base_dir / tar_name
    if tar_path.exists():
        tar_path.unlink()
    print(f"Creando archivo TAR.GZ: {tar_path}")
    # use shutil.make_archive with 'gztar' format
    shutil.make_archive(str(tar_path.with_suffix("")), "gztar", root_dir=base_dir)
    print("TAR.GZ generado correctamente.")


def main():
    # asume que se ejecuta desde Backend/ (pero no depende del cwd)
    BASE_DIR = Path(__file__).resolve().parent.parent
    print(f"Ejecutando en BASE_DIR: {BASE_DIR}")
    if BASE_DIR.name.lower() != 'backend':
        print(f"⚠️  Advertencia: BASE_DIR inesperado ({BASE_DIR}). Asegúrate de ejecutar el script dentro de la carpeta Backend.")
    total_size = sum(f.stat().st_size for f in BASE_DIR.rglob('*') if f.is_file())
    print(f"Tamaño total actual del proyecto: {total_size} bytes")

    print("=== Limpieza de archivos innecesarios ===")
    # eliminar cualquier paquete previo y archivos temporales
    patterns = ["*.env", "__pycache__", "*.pyc", "*.log", "staticfiles", "*.zip", "*.tar", "backend_*.tar*", "backend_*.zip"]
    remove_patterns(BASE_DIR, patterns)

    print("\n=== Asegurar .gitignore ===")
    ensure_gitignore(BASE_DIR)

    print("\n=== Empaquetar proyecto ===")
    make_zip(BASE_DIR, "backend_delcochile_v1.zip")
    make_tar(BASE_DIR, "backend_delcochile_v1.tar.gz")

    print("\n✅ Preparación completada. Se generaron los paquetes ZIP y TAR. Sube el que necesites a cPanel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
