"""Reimporta SIM y MODEMS para completar filas fallidas por lock."""
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
    print('Antes:', 'M', Medidor.objects.count(), 'S', SimCard.objects.count(), 'Mo', Modem.objects.count(), flush=True)

    files = [
        ('SIM', r'C:\Users\DELCOCHILE\Downloads\Maestro SIM 20260331.xlsx'),
        ('MODEMS', r'C:\Users\DELCOCHILE\Downloads\Maestro Módem.xlsx'),
    ]
    for tipo, path in files:
        print('=' * 60, tipo, flush=True)
        imp = importar_equipos_excel(load(path), user, tipo)
        print(imp.observaciones, flush=True)
        if imp.fallidas:
            for motivo in ImportacionExcelError.objects.filter(importacion=imp).values_list('motivo', flat=True)[:6]:
                print(' -', str(motivo)[:200], flush=True)

    print('Despues:', 'M', Medidor.objects.count(), 'S', SimCard.objects.count(), 'Mo', Modem.objects.count(), flush=True)
    print('Series medidor unicas', Medidor.objects.values('serie').distinct().count(), flush=True)
    print('IMEI sim unicos', SimCard.objects.values('imei').distinct().count(), flush=True)
    print('Series modem unicas', Modem.objects.values('serie').distinct().count(), flush=True)


if __name__ == '__main__':
    main()
