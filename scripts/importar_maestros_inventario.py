"""Importa maestros de inventario desde rutas fijas (uso puntual)."""
import os
import sys
from io import BytesIO

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from importaciones.models import ImportacionExcelError
from importaciones.utils import importar_equipos_excel
from inventario.models import Medidor, Modem, SimCard

Usuario = get_user_model()


def load(path: str) -> BytesIO:
    with open(path, 'rb') as handle:
        buf = BytesIO(handle.read())
    buf.name = os.path.basename(path)
    return buf


def main():
    user = (
        Usuario.objects.filter(rol='ADMIN', is_active=True).first()
        or Usuario.objects.filter(is_active=True).first()
    )
    print(f'Usuario importacion: {user}', flush=True)

    files = [
        ('MEDIDORES', r'C:\Users\DELCOCHILE\Downloads\Medidores 20260331.xlsx'),
        ('SIM', r'C:\Users\DELCOCHILE\Downloads\Maestro SIM 20260331.xlsx'),
        ('MODEMS', r'C:\Users\DELCOCHILE\Downloads\Maestro Módem.xlsx'),
    ]

    for tipo, path in files:
        print('=' * 60, tipo, flush=True)
        print('Archivo:', path, 'exists=', os.path.exists(path), flush=True)
        imp = importar_equipos_excel(load(path), user, tipo)
        print(imp.observaciones, '|', imp.estado, '| ok=', imp.exitosas, '| fail=', imp.fallidas, flush=True)
        if imp.fallidas:
            for motivo in ImportacionExcelError.objects.filter(importacion=imp).values_list('motivo', flat=True)[:8]:
                print(' -', str(motivo)[:220], flush=True)

    print('=' * 60, flush=True)
    print('DB Medidores', Medidor.objects.count(), flush=True)
    print('DB SIM', SimCard.objects.count(), flush=True)
    print('DB Modems', Modem.objects.count(), flush=True)

    print('REIMPORT MEDIDORES', flush=True)
    imp = importar_equipos_excel(load(files[0][1]), user, 'MEDIDORES')
    print(imp.observaciones, flush=True)
    print('DB Medidores after', Medidor.objects.count(), flush=True)


if __name__ == '__main__':
    main()
