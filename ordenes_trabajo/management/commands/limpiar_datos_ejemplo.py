from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q


CATALOGO_DIAGNOSTICO_INICIAL = [
    ('SISTEMA', 'IP errónea del módem', 'Actualizar IP en StarBeat'),
    ('SISTEMA', 'Base de datos no actualizada', 'Actualizar medidor en StarBeat'),
    ('SISTEMA', 'Caída masiva', 'Generar incidencia a TI'),
    ('SIMCARD', 'Sin plan de datos', 'Cambio de SIMCard'),
    ('SIMCARD', 'SIM sucia o mal instalada', 'Limpieza y reinstalación'),
    ('SIMCARD', 'SIM dañada', 'Cambio de SIMCard'),
    ('SIMCARD', 'Sin cobertura', 'Traslado de equipo, cambio de antena o uso de doble SIM'),
    ('MODEM', 'Obsoleto o con falla sin repuesto', 'Cambio de módem'),
    ('MODEM', 'Desprogramado', 'Cambio de módem y reprogramación del equipo retirado'),
    ('MODEM', 'Falla franca', 'Cambio de módem y baja del equipo retirado'),
    ('MODEM', 'No existe módem en terreno', 'Instalación de módem y habilitación de telemedida'),
    ('MEDIDOR', 'Hurto o intervención', 'Informar a Pérdidas'),
    ('MEDIDOR', 'No compatible con telemedida', 'Cambio de medidor'),
    ('MEDIDOR', 'Sin medidor, conectado directo', 'Instalar medidor, habilitar telemedida e informar a Pérdidas'),
    ('MEDIDOR', 'No comunica, pero registra', 'Cambio de medidor'),
    ('MEDIDOR', 'Falla franca, no comunica ni registra', 'Cambio de medidor e informar a Pérdidas'),
    ('MEDIDOR', 'Sin medidor', 'Reponer medidor si corresponde'),
    ('MEDIDOR', 'Medidor en terreno distinto al sistema', 'Actualizar sistema con medidor real en terreno'),
    ('ESTADO_CLIENTE', 'Sin suministro', 'Monitorear estado'),
    ('ESTADO_CLIENTE', 'Retirado', 'Retirar cliente con apoyo de Morosidad'),
    ('ESTADO_VISITA', 'Cerrado', 'Reprogramar visita para lograr acceso y diagnóstico'),
    ('ESTADO_VISITA', 'Deshabitado', 'Realizar seguimiento con lectura pedestre'),
    ('ESTADO_VISITA', 'No permite acceso', 'Reportar a Pérdidas o área correspondiente'),
]


class Command(BaseCommand):
    help = (
        'Elimina datos de prueba o resetea la plataforma operativa. '
        'Con --reset-completo deja en blanco OT, MoreApp, inventario, clientes, '
        'auditoría y catálogo (conserva usuarios y estados de inventario). '
        'Con --conservar-clientes hace el mismo reset operativo pero mantiene '
        'clientes e historial de proyectos.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué se eliminaría sin borrar nada.',
        )
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Confirmar eliminación sin preguntar.',
        )
        parser.add_argument(
            '--reset-completo',
            action='store_true',
            help='Borra todo el dato operativo: OT, MoreApp, inventario, clientes, auditoría y catálogo.',
        )
        parser.add_argument(
            '--conservar-clientes',
            action='store_true',
            help=(
                'Como --reset-completo, pero conserva Cliente e historial de proyectos. '
                'Borra OT, MoreApp, inventario, auditoría, importaciones y catálogo.'
            ),
        )
        parser.add_argument(
            '--flujo-operativo',
            action='store_true',
            help='Borra todas las OT, registros MoreApp y movimientos generados por MoreApp.',
        )
        parser.add_argument(
            '--incluir-moreapp',
            action='store_true',
            help='(Legado) Igual que --flujo-operativo para registros MoreApp.',
        )
        parser.add_argument(
            '--incluir-inventario-prueba',
            action='store_true',
            help='Además elimina equipos de prueba (MOD-*, IMEI 35..., medidores TEST).',
        )
        parser.add_argument(
            '--resembrar-catalogo',
            action='store_true',
            help='Tras reset, vuelve a cargar el catálogo de diagnósticos base.',
        )

    def _conteo_reportes(self):
        from reportes.services import REPORT_CATALOG, run_report

        return {slug: len(run_report(slug, {})[1]) for slug in REPORT_CATALOG}

    def _resumen_reset_completo(self, conservar_clientes=False):
        from ordenes_trabajo.models import (
            AdjuntoOrden,
            InformeCliente,
            IntegracionMoreApp,
            OrdenTrabajo,
        )
        from inventario.models import (
            Medidor,
            Modem,
            MovimientoInventario,
            SimCard,
            Ubicacion,
        )
        from clientes.models import Cliente, ClienteProyectoHistorial
        from web.models import AuditLog
        from catalogos.models import CatalogoDiagnostico
        from importaciones.models import ImportacionExcel

        resumen = [
            ('Órdenes de trabajo', OrdenTrabajo.objects.count()),
            ('Adjuntos de OT', AdjuntoOrden.objects.count()),
            ('Informes de cliente', InformeCliente.objects.count()),
            ('Registros MoreApp', IntegracionMoreApp.objects.count()),
            ('Movimientos de inventario', MovimientoInventario.objects.count()),
            ('Medidores', Medidor.objects.count()),
            ('Módems', Modem.objects.count()),
            ('SIM Cards', SimCard.objects.count()),
            ('Eventos de auditoría', AuditLog.objects.count()),
            ('Catálogo diagnósticos', CatalogoDiagnostico.objects.count()),
            ('Importaciones Excel', ImportacionExcel.objects.count()),
            ('Ubicaciones', Ubicacion.objects.count()),
        ]
        if conservar_clientes:
            resumen.append(('Clientes (SE CONSERVAN)', Cliente.objects.count()))
            resumen.append(
                ('Historial proyectos (SE CONSERVA)', ClienteProyectoHistorial.objects.count())
            )
        else:
            resumen.append(('Clientes', Cliente.objects.count()))
            resumen.append(('Historial proyectos', ClienteProyectoHistorial.objects.count()))

        try:
            from soporte.models import TicketSoporte
            resumen.append(('Tickets de soporte', TicketSoporte.objects.count()))
        except Exception:
            pass

        return resumen

    def _resumen_flujo_operativo(self):
        from ordenes_trabajo.models import (
            AdjuntoOrden,
            InformeCliente,
            IntegracionMoreApp,
            OrdenTrabajo,
        )
        from inventario.models import MovimientoInventario

        return [
            ('Órdenes de trabajo', OrdenTrabajo.objects.count()),
            ('Adjuntos de OT', AdjuntoOrden.objects.count()),
            ('Informes de cliente', InformeCliente.objects.count()),
            ('Registros MoreApp', IntegracionMoreApp.objects.count()),
            ('Movimientos MoreApp', MovimientoInventario.objects.filter(origen_sistema='MOREAPP').count()),
        ]

    def _resumen_ejemplo_parcial(self):
        from ordenes_trabajo.models import OrdenTrabajo
        from inventario.models import Medidor, Modem, SimCard
        from clientes.models import Cliente

        ot_qs = OrdenTrabajo.objects.filter(
            Q(titulo__icontains='MoreApp')
            | Q(titulo__icontains='ejemplo')
            | Q(titulo__icontains='prueba')
            | Q(titulo__icontains='demo')
            | Q(titulo__istartswith='OT ')
            | Q(titulo__istartswith='Trabajo —')
        )
        clientes_qs = Cliente.objects.filter(
            Q(numero_cliente__icontains='CLI-OT')
            | Q(numero_cliente__icontains='CLI-VAL')
            | Q(numero_cliente__icontains='CLI-SYNC')
            | Q(numero_cliente__icontains='EJEMPLO')
        )
        modems_qs = Modem.objects.filter(
            Q(observaciones__icontains='prueba')
            | Q(serie__istartswith='MOD-')
        )
        sims_qs = SimCard.objects.filter(imei__regex=r'^35\d{10}$')
        medidores_test_qs = Medidor.objects.filter(
            Q(serie__icontains='TEST')
            | Q(serie__istartswith='MED-TEST')
            | Q(serie='NONE_TEST')
        )

        return [
            ('Órdenes de trabajo de ejemplo', ot_qs.count()),
            ('Clientes de prueba', clientes_qs.count()),
            ('Módems generados de prueba', modems_qs.count()),
            ('SIM con IMEI aleatorio (35...)', sims_qs.count()),
            ('Medidores de prueba', medidores_test_qs.count()),
        ], {
            'ot_qs': ot_qs,
            'clientes_qs': clientes_qs,
            'modems_qs': modems_qs,
            'sims_qs': sims_qs,
            'medidores_test_qs': medidores_test_qs,
        }

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        reset_completo = options['reset_completo']
        conservar_clientes = options['conservar_clientes']
        flujo_operativo = options['flujo_operativo'] or options['incluir_moreapp']
        incluir_inventario_prueba = options['incluir_inventario_prueba']
        resembrar_catalogo = options['resembrar_catalogo']
        auto_confirm = options['yes']

        if reset_completo and conservar_clientes:
            self.stdout.write(self.style.ERROR(
                'No combines --reset-completo con --conservar-clientes. '
                'Usa solo --conservar-clientes.'
            ))
            return

        modo_reset = reset_completo or conservar_clientes

        if conservar_clientes:
            resumen = self._resumen_reset_completo(conservar_clientes=True)
            self.stdout.write(
                'Reset operativo CONSERVANDO clientes e historial de proyectos '
                '(también conserva usuarios y estados de inventario):'
            )
        elif reset_completo:
            resumen = self._resumen_reset_completo(conservar_clientes=False)
            self.stdout.write(
                'Reset completo (conserva usuarios y estados de inventario de referencia):'
            )
        elif flujo_operativo:
            resumen = self._resumen_flujo_operativo()
            self.stdout.write('Limpieza de flujo operativo (conserva clientes importados e inventario maestro):')
        else:
            resumen, _ = self._resumen_ejemplo_parcial()
            self.stdout.write('Limpieza parcial de datos de ejemplo:')

        for etiqueta, cantidad in resumen:
            self.stdout.write(f'  - {etiqueta}: {cantidad}')

        if incluir_inventario_prueba and not modo_reset:
            _, qs_map = self._resumen_ejemplo_parcial()
            self.stdout.write('\nInventario de prueba adicional:')
            for etiqueta, cantidad in [
                ('Módems generados de prueba', qs_map['modems_qs'].count()),
                ('SIM con IMEI aleatorio (35...)', qs_map['sims_qs'].count()),
                ('Medidores de prueba', qs_map['medidores_test_qs'].count()),
                ('Clientes de prueba sin OT', qs_map['clientes_qs'].count()),
            ]:
                self.stdout.write(f'  - {etiqueta}: {cantidad}')

        reportes = self._conteo_reportes()
        con_datos = {slug: n for slug, n in reportes.items() if n > 0}
        self.stdout.write('\nReportes operativos con filas:')
        if con_datos:
            for slug, n in con_datos.items():
                self.stdout.write(f'  - {slug}: {n}')
        else:
            self.stdout.write('  (todos vacíos)')

        if dry_run:
            self.stdout.write(self.style.WARNING('Modo dry-run: no se eliminó nada.'))
            return

        if not any(c for _, c in resumen if c > 0) and not incluir_inventario_prueba and not modo_reset:
            self.stdout.write(self.style.SUCCESS('No hay datos que borrar con los filtros seleccionados.'))
            return

        confirmar = auto_confirm
        if not confirmar:
            if conservar_clientes:
                prompt = '¿Confirmar reset conservando clientes/proyectos? [s/N]: '
            elif reset_completo:
                prompt = '¿Confirmar eliminación TOTAL? [s/N]: '
            else:
                prompt = '¿Confirmar eliminación? [s/N]: '
            confirmar = input(prompt).strip().lower() in ('s', 'si', 'sí', 'y', 'yes')
        if not confirmar:
            self.stdout.write(self.style.WARNING('Operación cancelada.'))
            return

        with transaction.atomic():
            if modo_reset:
                self._limpiar_reset_completo(conservar_clientes=conservar_clientes)
                if resembrar_catalogo:
                    self._resembrar_catalogo_diagnostico()
            elif flujo_operativo:
                self._limpiar_flujo_operativo()
            else:
                self._limpiar_ejemplo_parcial()

            if incluir_inventario_prueba and not modo_reset:
                self._limpiar_inventario_prueba()

            if modo_reset:
                self._reiniciar_secuencias_tras_limpieza(
                    reset_completo=True,
                    conservar_clientes=conservar_clientes,
                )
            elif flujo_operativo:
                self._reiniciar_secuencias_tras_limpieza(flujo_operativo=True)

        if conservar_clientes:
            self.stdout.write(self.style.SUCCESS(
                'Reset operativo finalizado. Clientes e historial de proyectos se mantuvieron.'
            ))
            self.stdout.write('  Conservado: clientes, historial de proyectos, usuarios y estados de inventario.')
            self.stdout.write('  Borrado: OT, MoreApp, inventario, auditoría, importaciones y catálogo.')
            if not resembrar_catalogo:
                self.stdout.write(
                    '  Catálogo de diagnósticos vacío. Usa --resembrar-catalogo si quieres la lista base.'
                )
        elif reset_completo:
            self.stdout.write(self.style.SUCCESS(
                'Reset completo finalizado. La plataforma quedó en blanco para pruebas manuales.'
            ))
            self.stdout.write('  Conservado: usuarios y estados de inventario (catálogo de estados).')
            self.stdout.write('  Siguiente paso sugerido: importar clientes/equipos o crear OT desde cero.')
            if not resembrar_catalogo:
                self.stdout.write(
                    '  Catálogo de diagnósticos vacío. Usa --resembrar-catalogo si quieres la lista base.'
                )
        else:
            self.stdout.write(self.style.SUCCESS(
                'Limpieza finalizada. Puedes crear OT nuevas y volver a sincronizar MoreApp.'
            ))

    def _eliminar_moreapp_y_ot(self):
        from ordenes_trabajo.models import (
            AdjuntoOrden,
            InformeCliente,
            IntegracionMoreApp,
            OrdenTrabajo,
        )

        if IntegracionMoreApp.objects.exists():
            deleted_ma, _ = IntegracionMoreApp.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Registros MoreApp eliminados: {deleted_ma}'))

        if OrdenTrabajo.objects.exists():
            deleted_adj, _ = AdjuntoOrden.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Adjuntos eliminados: {deleted_adj}'))
            deleted_inf, _ = InformeCliente.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Informes eliminados: {deleted_inf}'))
            deleted_ot, _ = OrdenTrabajo.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Órdenes eliminadas: {deleted_ot}'))

    def _reset_sqlite_sequences(self, table_names):
        from django.db import connection

        if connection.vendor != 'sqlite' or not table_names:
            return

        with connection.cursor() as cursor:
            for table in table_names:
                cursor.execute('DELETE FROM sqlite_sequence WHERE name = %s', [table])
        self.stdout.write(self.style.SUCCESS(
            f'Secuencias SQLite reiniciadas: {", ".join(table_names)}'
        ))

    def _reiniciar_secuencias_tras_limpieza(
        self, flujo_operativo=False, reset_completo=False, conservar_clientes=False,
    ):
        tablas = []
        if flujo_operativo or reset_completo:
            tablas.extend([
                'ordenes_trabajo_ordentrabajo',
                'ordenes_trabajo_integracionmoreapp',
                'ordenes_trabajo_adjuntoorden',
                'ordenes_trabajo_informecliente',
            ])
        if reset_completo:
            tablas.extend([
                'inventario_medidor',
                'inventario_modem',
                'inventario_simcard',
                'inventario_movimientoinventario',
                'inventario_movimientoitem',
                'inventario_ubicacion',
                'web_auditlog',
                'importaciones_importacionexcel',
                'importaciones_importacionexcelerror',
                'catalogos_catalogodiagnostico',
            ])
            if not conservar_clientes:
                tablas.extend([
                    'clientes_cliente',
                    'clientes_clienteproyectohistorial',
                ])
        self._reset_sqlite_sequences(tablas)

    def _limpiar_flujo_operativo(self):
        from inventario.models import MovimientoInventario

        mov_qs = MovimientoInventario.objects.filter(origen_sistema='MOREAPP')
        if mov_qs.exists():
            deleted_mov, _ = mov_qs.delete()
            self.stdout.write(self.style.SUCCESS(f'Movimientos MoreApp eliminados: {deleted_mov}'))

        self._eliminar_moreapp_y_ot()

    def _limpiar_reset_completo(self, conservar_clientes=False):
        from inventario.models import (
            Medidor,
            Modem,
            MovimientoInventario,
            SimCard,
            Ubicacion,
        )
        from clientes.models import Cliente, ClienteProyectoHistorial
        from web.models import AuditLog
        from catalogos.models import CatalogoDiagnostico
        from importaciones.models import ImportacionExcel

        self._eliminar_moreapp_y_ot()

        if MovimientoInventario.objects.exists():
            deleted_mov, _ = MovimientoInventario.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Movimientos de inventario eliminados: {deleted_mov}'))

        # Desvincular medidor actual para poder borrar inventario sin tocar clientes
        n_desv = Cliente.objects.exclude(medidor_actual=None).update(medidor_actual=None)
        if n_desv:
            self.stdout.write(self.style.SUCCESS(
                f'Clientes desvinculados de medidor_actual: {n_desv}'
            ))

        for modelo, etiqueta in (
            (SimCard, 'SIM Cards'),
            (Modem, 'Módems'),
            (Medidor, 'Medidores'),
        ):
            if modelo.objects.exists():
                deleted, _ = modelo.objects.all().delete()
                self.stdout.write(self.style.SUCCESS(f'{etiqueta} eliminados: {deleted}'))

        if conservar_clientes:
            n_cli = Cliente.objects.count()
            n_hist = ClienteProyectoHistorial.objects.count()
            self.stdout.write(self.style.WARNING(
                f'Conservados: {n_cli} clientes y {n_hist} registros de historial de proyectos.'
            ))
        elif Cliente.objects.exists():
            deleted_cli, _ = Cliente.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Clientes eliminados: {deleted_cli}'))

        if AuditLog.objects.exists():
            deleted_audit, _ = AuditLog.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Eventos de auditoría eliminados: {deleted_audit}'))

        if CatalogoDiagnostico.objects.exists():
            deleted_cat, _ = CatalogoDiagnostico.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Catálogo diagnósticos eliminado: {deleted_cat}'))

        if ImportacionExcel.objects.exists():
            deleted_imp, _ = ImportacionExcel.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Importaciones Excel eliminadas: {deleted_imp}'))

        try:
            from soporte.models import TicketSoporte
            if TicketSoporte.objects.exists():
                deleted_tk, _ = TicketSoporte.objects.all().delete()
                self.stdout.write(self.style.SUCCESS(f'Tickets de soporte eliminados: {deleted_tk}'))
        except Exception:
            pass

        if Ubicacion.objects.exists():
            deleted_ubi, _ = Ubicacion.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Ubicaciones eliminadas: {deleted_ubi}'))

        from django.core.management import call_command
        call_command('inicializar_estados', verbosity=0)

    def _resembrar_catalogo_diagnostico(self):
        from catalogos.models import CatalogoDiagnostico

        creados = 0
        for orden, (categoria, origen, solucion) in enumerate(CATALOGO_DIAGNOSTICO_INICIAL, start=1):
            _, created = CatalogoDiagnostico.objects.get_or_create(
                categoria=categoria,
                origen=origen,
                defaults={'solucion': solucion, 'orden': orden, 'activo': True},
            )
            if created:
                creados += 1
        self.stdout.write(self.style.SUCCESS(
            f'Catálogo de diagnósticos resembrado ({creados} entradas nuevas).'
        ))

    def _limpiar_ejemplo_parcial(self):
        from ordenes_trabajo.models import (
            AdjuntoOrden,
            InformeCliente,
            IntegracionMoreApp,
            OrdenTrabajo,
        )
        from clientes.models import Cliente

        _, qs_map = self._resumen_ejemplo_parcial()
        ot_qs = qs_map['ot_qs']
        ot_ids = list(ot_qs.values_list('pk', flat=True))
        if ot_ids:
            AdjuntoOrden.objects.filter(orden_id__in=ot_ids).delete()
            InformeCliente.objects.filter(orden_id__in=ot_ids).delete()
            IntegracionMoreApp.objects.filter(orden_id__in=ot_ids).update(orden=None)
            deleted_ot, _ = ot_qs.delete()
            self.stdout.write(self.style.SUCCESS(f'Órdenes de ejemplo eliminadas: {deleted_ot}'))

        clientes_qs = qs_map['clientes_qs']
        if clientes_qs.exists():
            seguros = [cliente.pk for cliente in clientes_qs if not cliente.ordenes.exists()]
            if seguros:
                deleted_cli, _ = Cliente.objects.filter(pk__in=seguros).delete()
                self.stdout.write(self.style.SUCCESS(f'Clientes de prueba eliminados: {deleted_cli}'))

    def _limpiar_inventario_prueba(self):
        from clientes.models import Cliente
        from inventario.models import Medidor, Modem, SimCard

        _, qs_map = self._resumen_ejemplo_parcial()
        modems_qs = qs_map['modems_qs']
        sims_qs = qs_map['sims_qs']
        medidores_test_qs = qs_map['medidores_test_qs']
        clientes_qs = qs_map['clientes_qs']

        if modems_qs.exists():
            deleted_mod, _ = modems_qs.delete()
            self.stdout.write(self.style.SUCCESS(f'Módems de prueba eliminados: {deleted_mod}'))

        if sims_qs.exists():
            deleted_sim, _ = sims_qs.delete()
            self.stdout.write(self.style.SUCCESS(f'SIM de prueba eliminadas: {deleted_sim}'))

        if medidores_test_qs.exists():
            Cliente.objects.filter(
                medidor_actual_id__in=medidores_test_qs.values_list('pk', flat=True)
            ).update(medidor_actual=None)
            deleted_med, _ = medidores_test_qs.delete()
            self.stdout.write(self.style.SUCCESS(f'Medidores de prueba eliminados: {deleted_med}'))

        if clientes_qs.exists():
            seguros = [cliente.pk for cliente in clientes_qs if not cliente.ordenes.exists()]
            if seguros:
                deleted_cli, _ = Cliente.objects.filter(pk__in=seguros).delete()
                self.stdout.write(self.style.SUCCESS(f'Clientes de prueba eliminados: {deleted_cli}'))
