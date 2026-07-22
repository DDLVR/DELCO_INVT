from django.conf import settings
from django.test import SimpleTestCase, override_settings
from pathlib import Path
import tempfile

from integraciones.moreapp_media import (
    asociar_archivos_locales,
    enriquecer_datos_media,
    extraer_fotos_desde_payload,
    extraer_geo_desde_payload,
)


class MoreAppMediaPunto6Tests(SimpleTestCase):
    def test_extrae_gps_y_fotos_gridfs(self):
        payload = {
            'data': {
                'location': {
                    'coordinates': {'latitude': -33.45, 'longitude': -70.66},
                    'formattedValue': 'Santiago, Chile',
                },
                'fotoDeSeguridad': 'gridfs://registrationFiles/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
                'caratulaDeMedidor': 'gridfs://registrationFiles/11111111-2222-3333-4444-555555555555',
                'observacin': 'ok',
            }
        }
        geo = extraer_geo_desde_payload(payload)
        self.assertEqual(geo['latitude'], -33.45)
        self.assertIn('google.com/maps', geo['maps_url'])
        fotos = extraer_fotos_desde_payload(payload)
        self.assertEqual(len(fotos), 2)
        self.assertFalse(fotos[0]['disponible'])

    def test_asocia_archivo_local_por_uuid(self):
        with tempfile.TemporaryDirectory() as tmp:
            uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
            img = Path(tmp) / f'evidencia-{uuid}.jpg'
            img.write_bytes(b'\xff\xd8\xff\xd9')  # jpeg minimo
            fotos = [{
                'campo': 'fotoDeSeguridad',
                'label': 'Foto De Seguridad',
                'gridfs_ref': f'gridfs://registrationFiles/{uuid}',
                'gridfs_id': uuid,
                'url': '',
                'nombre_archivo': '',
                'ruta_local': '',
                'media_url': '',
                'disponible': False,
            }]
            with override_settings(MEDIA_ROOT=tmp + '/media', MEDIA_URL='/media/'):
                Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
                out = asociar_archivos_locales(fotos, tmp, 'sub-test-1')
            self.assertTrue(out[0]['disponible'])
            self.assertTrue(out[0]['media_url'].startswith('/media/'))

    def test_enriquecer_datos_media_incluye_contadores(self):
        payload = {
            'data': {
                'location': {
                    'coordinates': {'latitude': 1.0, 'longitude': 2.0},
                    'formattedValue': 'X',
                },
                'fotoEmpalme': 'gridfs://registrationFiles/abcdefab-cdef-abcd-efab-cdefabcdefab',
            }
        }
        out = enriquecer_datos_media({}, payload, '', 'abc')
        self.assertEqual(out['fotos_total'], 1)
        self.assertEqual(out['fotos_disponibles'], 0)
        self.assertIn('geo', out)
