"""
Utilidades para importación desde Excel
"""

import openpyxl
from importaciones.models import ImportacionExcel, ImportacionExcelError
from inventario.models import Medidor, SimCard, Modem, EstadoInventario, Ubicacion, MovimientoInventario, MovimientoItem
from clientes.models import Cliente
from usuarios.models import Usuario


def importar_equipos_excel(archivo, usuario, tipo_equipo='MEDIDORES'):
    """
    Importa equipos (Medidores, SIM, Módems) desde archivo Excel.
    
    Formato esperado:
    - Medidores: serie, marca, modelo, identificador_interno (opcional)
    - SIM: msisdn, proveedor, serie_plastico, ip_fija (opcional)
    - Módems: fecha_recepcion, bodega, marca, caja, serie, modulo
    
    Retorna: ImportacionExcel instance
    """
    from datetime import datetime

    def registrar_movimiento_importacion(equipo_obj, tipo_item, estado_obj_local, detalle, fila):
        try:
            movimiento = MovimientoInventario.objects.create(
                tipo='IMPORTACION',
                origen=bodega,
                destino=bodega,
                responsable=usuario,
                observacion=f'Importación masiva {tipo_item} fila {fila}: {detalle}',
            )
            item_kwargs = {
                'movimiento': movimiento,
                'tipo_equipo': tipo_item,
                'cantidad': 1,
            }
            if tipo_item == 'MEDIDOR':
                item_kwargs['medidor'] = equipo_obj
            elif tipo_item == 'SIM':
                item_kwargs['simcard'] = equipo_obj
            else:
                item_kwargs['modem'] = equipo_obj
            MovimientoItem.objects.create(**item_kwargs)
        except Exception:
            # No interrumpir importación si falla el registro de trazabilidad
            pass
    
    # Crear registro de importación
    importacion = ImportacionExcel.objects.create(
        tipo='EQUIPOS',
        archivo_original=archivo.name if hasattr(archivo, 'name') else 'Upload',
        usuario=usuario,
    )
    
    try:
        # Cargar workbook
        wb = openpyxl.load_workbook(archivo)
        ws = wb.active
        
        # Leer headers de la primera fila para debugging
        headers = [cell.value for cell in ws[1]]
        print(f"[DEBUG] Headers encontrados: {headers}")
        
        # Ubicación por defecto (Bodega)
        bodega = Ubicacion.objects.filter(nombre__icontains='Bodega').first()
        if not bodega:
            bodega = Ubicacion.objects.create(
                tipo='BODEGA_DELCO',
                nombre='Bodega Principal'
            )
        
        # Estado por defecto (Bodega)
        estado = EstadoInventario.objects.filter(nombre='En bodega').first()
        if not estado:
            estado = EstadoInventario.objects.create(nombre='En bodega')
        
        contador_filas = 0
        exitosas = 0
        fallidas = 0
        
        # Iterar filas (saltando header)
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=False), start=2):
            contador_filas += 1
            
            try:
                valores = [cell.value for cell in row]
                
                # DEBUG: Mostrar primera fila con datos para diagnóstico
                if idx == 2:
                    print(f"[DEBUG] Primera fila de datos (fila {idx}): {valores}")
                
                # Validar que la fila no esté vacía (al menos las primeras 3 columnas deben tener datos)
                if not any(valores[:3]):
                    continue
                
                # Si la primera columna está vacía, probablemente terminaron los datos reales
                if not valores[0]:
                    continue
                
                # Procesar según tipo de equipo
                if tipo_equipo.upper() == 'MEDIDORES':
                    # Formato real planilla medidores:
                    # #, fecha_recepcion, bodega, marca, caja, medidor, modulo, fecha_entrega, entregado_a, estado, cliente
                    while len(valores) < 11:
                        valores.append(None)

                    correlativo = valores[0]
                    fecha_recepcion = valores[1]
                    bodega_ref = valores[2]
                    marca = valores[3]
                    caja = valores[4]
                    serie = valores[5]
                    modulo = valores[6]
                    fecha_entrega = valores[7]
                    entregado_a_nombre = valores[8]
                    estado_nombre = valores[9]
                    cliente_numero = valores[10]

                    # Validar campos obligatorios reales
                    if not all([fecha_recepcion, serie]):
                        raise ValueError('Faltan campos requeridos: fecha_recepcion, serie')

                    # Convertir serie y caja a string (pero serie debe ser igual a columna Medidor)
                    serie = str(serie).strip() if serie else None
                    caja = str(caja).strip() if caja else None
                    marca = str(marca).strip() if marca else None  # Igual a planilla

                    # Convertir fecha de recepción de forma tolerante
                    from datetime import datetime, date
                    if isinstance(fecha_recepcion, datetime):
                        fecha_recepcion = fecha_recepcion.date()
                    elif isinstance(fecha_recepcion, date):
                        pass
                    else:
                        # Si es string tipo 'datetime.datetime(YYYY, MM, DD, ...)', convertir a DD/MM/YYYY (robusto)
                        if isinstance(fecha_recepcion, str) and 'datetime.datetime' in fecha_recepcion:
                            import re
                            fr = fecha_recepcion.replace("'", "").replace('"', '').replace('\\u0027', '').replace('\\', '').strip()
                            match = re.search(r'datetime\.datetime\s*\(\s*(\d+),\s*(\d+),\s*(\d+)', fr)
                            if match:
                                y, m, d = match.groups()
                                fecha_recepcion = f"{int(d):02d}/{int(m):02d}/{y}"
                        formatos = ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%m/%d/%Y']
                        convertido = False
                        for fmt in formatos:
                            try:
                                fecha_recepcion = datetime.strptime(str(fecha_recepcion).strip(), fmt).date()
                                convertido = True
                                break
                            except Exception:
                                continue
                        if not convertido:
                            # Si no se pudo convertir, dejar como None (vacío)
                            fecha_recepcion = None

                    # Convertir modulo desde texto SI/NO a booleano para el modelo
                    if isinstance(modulo, str):
                        modulo = modulo.strip().lower()
                        if modulo in ['si', 'sí', 'yes', 'true', '1']:
                            modulo = True
                        elif modulo in ['no', 'false', '0']:
                            modulo = False
                        else:
                            modulo = None
                    elif isinstance(modulo, (int, bool)):
                        modulo = bool(modulo)
                    else:
                        modulo = None

                    # Validar unicidad de serie
                    if Medidor.objects.filter(serie=serie).exists():
                        raise ValueError(f'Medidor con serie {serie} ya existe')

                    # Buscar estado si viene
                    estado_obj = None
                    if estado_nombre:
                        estado_nombre_str = str(estado_nombre).strip()
                        estado_obj = EstadoInventario.objects.filter(nombre__icontains=estado_nombre_str).first()
                    if not estado_obj:
                        estado_obj = estado

                    # Cliente por número (desde planilla)
                    cliente_obj = None
                    if cliente_numero:
                        cliente_num_str = str(cliente_numero).strip()
                        cliente_obj = Cliente.objects.filter(numero_cliente=cliente_num_str).first()
                        if not cliente_obj:
                            cliente_obj = Cliente.objects.create(
                                numero_cliente=cliente_num_str,
                                direccion=f'Cliente {cliente_num_str}',
                                comuna='Por definir'
                            )

                    # Buscar usuario entregado_a si viene

                    # Guardar el valor textual de ENTREGADO A en entregado_a_info, no buscar usuario ni relacionar con clientes
                    entregado_a_info = str(entregado_a_nombre).strip() if entregado_a_nombre else ''

                    # Convertir fecha_entrega si viene, de forma tolerante
                    if fecha_entrega:
                        if isinstance(fecha_entrega, datetime):
                            fecha_entrega = fecha_entrega.date()
                        elif isinstance(fecha_entrega, date):
                            pass
                        else:
                            if isinstance(fecha_entrega, str) and 'datetime.datetime' in fecha_entrega:
                                import re
                                fe = fecha_entrega.replace("'", "").replace('"', '').replace('\\u0027', '').replace('\\', '').strip()
                                match = re.search(r'datetime\.datetime\s*\(\s*(\d+),\s*(\d+),\s*(\d+)', fe)
                                if match:
                                    y, m, d = match.groups()
                                    fecha_entrega = f"{int(d):02d}/{int(m):02d}/{y}"
                            formatos = ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%m/%d/%Y']
                            convertido = False
                            for fmt in formatos:
                                try:
                                    fecha_entrega = datetime.strptime(str(fecha_entrega).strip(), fmt).date()
                                    convertido = True
                                    break
                                except Exception:
                                    continue
                            if not convertido:
                                # Si no se pudo convertir, dejar como None (vacío)
                                fecha_entrega = None

                    # Crear medidor
                    medidor = Medidor.objects.create(
                        fecha_recepcion=fecha_recepcion,
                        bodega=str(bodega_ref).strip() if bodega_ref else '',
                        marca=marca,
                        caja=caja,
                        serie=serie,
                        modulo=modulo,
                        fecha_entrega=fecha_entrega,
                        entregado_a=None,
                        entregado_a_info=entregado_a_info,
                        estado_inventario=estado_obj,
                        cliente=cliente_obj,
                        ubicacion_actual=bodega
                    )
                    registrar_movimiento_importacion(
                        medidor,
                        'MEDIDOR',
                        estado_obj,
                        f'Serie {medidor.serie}',
                        idx,
                    )
                    # Guardar trazas textuales de cliente/correlativo en observaciones
                    observaciones = []
                    if correlativo:
                        observaciones.append(f"Correlativo: {correlativo}")
                    if observaciones:
                        medidor.observaciones = ' | '.join(observaciones)
                        medidor.save()
                
                elif tipo_equipo.upper() == 'SIM':
                    # Nuevo formato según imagen del usuario:
                    # Columnas: IMEI, OPERADOR, ABONADO, DIRECCIÓN IP, APN, FECHA DE RECEPCIÓN, ENTREGADO A
                    #          FECHA ENTREGA, ESTADO, CLIENTE, MEDIDOR
                    
                    # Asegurar que tenemos al menos 11 columnas
                    while len(valores) < 11:
                        valores.append(None)
                    
                    imei = valores[0]
                    operador = valores[1]
                    abonado = valores[2]
                    direccion_ip = valores[3]
                    apn = valores[4]
                    fecha_recepcion = valores[5]
                    entregado_a_nombre = valores[6]
                    
                    # Campos verdes (opcionales)
                    fecha_entrega = valores[7] if len(valores) > 7 else None
                    estado_nombre = valores[8] if len(valores) > 8 else None
                    cliente_numero = valores[9] if len(valores) > 9 else None
                    medidor_serie = valores[10] if len(valores) > 10 else None
                    
                    # Validar campos obligatorios amarillos
                    if not imei:
                        raise ValueError('Falta IMEI (columna A)')
                    if not operador:
                        raise ValueError('Falta OPERADOR (columna B)')
                    if not abonado:
                        raise ValueError('Falta ABONADO (columna C) - Verifica que la celda no esté vacía o con formato especial en Excel')
                    if not apn:
                        raise ValueError('Falta APN (columna E)')
                    if not fecha_recepcion:
                        raise ValueError('Falta FECHA DE RECEPCIÓN (columna F)')
                    
                    # Función helper para limpiar valores
                    def limpiar_valor(val):
                        if val is None:
                            return ''
                        # Convertir a string
                        val_str = str(val)
                        # Remover comillas al inicio y final
                        val_str = val_str.strip().strip("'").strip('"').strip()
                        return val_str
                    
                    # Convertir a string y limpiar - IMPORTANTE para números grandes
                    # Excel puede enviar números grandes como float (ej: 5.697373194e+10)
                    if isinstance(imei, (int, float)):
                        imei = f"{int(imei)}"  # Convertir a entero y luego a string sin notación científica
                    else:
                        imei = limpiar_valor(imei)
                    
                    operador = limpiar_valor(operador)
                    
                    # ABONADO puede ser número muy grande (ej: 56973719416)
                    if isinstance(abonado, (int, float)):
                        abonado = f"{int(abonado)}"  # Convertir sin notación científica
                    else:
                        abonado = limpiar_valor(abonado)
                    
                    # Verificar nuevamente después de limpiar
                    if not abonado or abonado == '':
                        raise ValueError('ABONADO (columna C) está vacío después de limpieza. Copia el valor directamente como texto en Excel y guarda de nuevo.')
                    
                    direccion_ip = limpiar_valor(direccion_ip) if direccion_ip else ''
                    apn = limpiar_valor(apn)
                    entregado_a_nombre = limpiar_valor(entregado_a_nombre) if entregado_a_nombre else ''
                    
                    # Verificar duplicados
                    if SimCard.objects.filter(imei=imei).exists():
                        raise ValueError(f'SIM con IMEI {imei} ya existe en base de datos')
                    
                    # Convertir fecha de recepción (Excel date o string)
                    try:
                        if isinstance(fecha_recepcion, datetime):
                            fecha_recepcion = fecha_recepcion.date()
                        elif hasattr(fecha_recepcion, 'date'):  # Si es un objeto datetime de openpyxl
                            fecha_recepcion = fecha_recepcion.date()
                        elif isinstance(fecha_recepcion, str):
                            from datetime import datetime
                            # Intentar varios formatos
                            fecha_ok = False
                            for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                                try:
                                    fecha_recepcion = datetime.strptime(fecha_recepcion.strip(), fmt).date()
                                    fecha_ok = True
                                    break
                                except:
                                    continue
                            if not fecha_ok:
                                raise ValueError(f'Formato de FECHA DE RECEPCIÓN no válido: {fecha_recepcion}')
                        else:
                            raise ValueError(f'Tipo de fecha no reconocido: {type(fecha_recepcion)}')
                    except Exception as e:
                        raise ValueError(f'Error en FECHA DE RECEPCIÓN (columna F): {str(e)}')
                    
                    # Convertir fecha de entrega si viene
                    if fecha_entrega:
                        try:
                            if isinstance(fecha_entrega, datetime):
                                fecha_entrega = fecha_entrega.date()
                            elif hasattr(fecha_entrega, 'date'):
                                fecha_entrega = fecha_entrega.date()
                            elif isinstance(fecha_entrega, str):
                                from datetime import datetime
                                for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                                    try:
                                        fecha_entrega = datetime.strptime(fecha_entrega.strip(), fmt).date()
                                        break
                                    except:
                                        continue
                        except:
                            fecha_entrega = None
                    
                    # Buscar estado si viene
                    estado_obj = None
                    if estado_nombre:
                        estado_nombre_str = str(estado_nombre).strip()
                        estado_obj = EstadoInventario.objects.filter(
                            nombre__icontains=estado_nombre_str
                        ).first()
                    
                    # Si no hay estado especificado, usar "Instalado" por defecto
                    if not estado_obj:
                        estado_obj = EstadoInventario.objects.filter(nombre='Instalado').first()
                        if not estado_obj:
                            estado_obj = EstadoInventario.objects.create(nombre='Instalado')
                    
                    # Buscar cliente si viene (por numero_cliente)
                    cliente_obj = None
                    if cliente_numero:
                        try:
                            cliente_num_str = str(cliente_numero).strip()
                            # Buscar por numero_cliente (campo correcto en modelo Cliente)
                            cliente_obj = Cliente.objects.filter(
                                numero_cliente=cliente_num_str
                            ).first()
                            
                            # Si no existe, crear el cliente
                            if not cliente_obj:
                                cliente_obj = Cliente.objects.create(
                                    numero_cliente=cliente_num_str,
                                    direccion=f'Cliente {cliente_num_str}',
                                    comuna='Por definir'
                                )
                        except:
                            pass  # Si falla, continuar sin cliente
                    
                    # Buscar medidor si viene
                    medidor_obj = None
                    if medidor_serie:
                        medidor_serie_str = str(medidor_serie).strip()
                        medidor_obj = Medidor.objects.filter(
                            serie=medidor_serie_str
                        ).first()
                    
                    # Crear SIM Card
                    sim = SimCard.objects.create(
                        imei=imei,
                        operador=operador,
                        abonado=abonado,
                        direccion_ip=direccion_ip,
                        apn=apn,
                        fecha_recepcion=fecha_recepcion,
                        entregado_a_nombre=entregado_a_nombre,
                        fecha_entrega=fecha_entrega,
                        estado_inventario=estado_obj,
                        cliente=cliente_obj,
                        medidor=medidor_obj,
                        ubicacion_actual=bodega
                    )
                    registrar_movimiento_importacion(
                        sim,
                        'SIM',
                        estado_obj,
                        f'IMEI {sim.imei}',
                        idx,
                    )
                
                elif tipo_equipo.upper() == 'MODEMS':
                    # Formato según imagen del usuario:
                    # VERDE (Excel): MARCA, MODELO, IMEI, SERIE, Fecha Recepción, Fecha Entrega, Caja, Técnico
                    # AZUL (admin): Cliente, Medidor, IP, Puerto, Marca, Obs, Retirado, Serie, Irregularidad, Proyecto
                    
                    # Asegurar que tenemos suficientes columnas
                    while len(valores) < 18:
                        valores.append(None)
                    
                    # Columnas VERDES (0-7)
                    marca = valores[0]
                    modelo = valores[1]
                    imei = valores[2]
                    serie = valores[3]
                    fecha_recepcion = valores[4]
                    fecha_entrega = valores[5]
                    caja = valores[6]
                    tecnico_responsable = valores[7]
                    
                    # Columnas editables/azules (8-17)
                    cliente_numero = valores[8] if len(valores) > 8 else None
                    medidor_serie = valores[9] if len(valores) > 9 else None
                    ip = valores[10] if len(valores) > 10 else None
                    puerto = valores[11] if len(valores) > 11 else None
                    marca_secundaria = valores[12] if len(valores) > 12 else None
                    observaciones = valores[13] if len(valores) > 13 else None
                    retirado = valores[14] if len(valores) > 14 else None
                    serie_secundaria = valores[15] if len(valores) > 15 else None
                    irregularidad = valores[16] if len(valores) > 16 else None
                    proyecto = valores[17] if len(valores) > 17 else None
                    
                    # Validar campos obligatorios
                    if not marca:
                        raise ValueError('Falta MARCA (columna A)')
                    if not serie:
                        raise ValueError('Falta SERIE (columna D)')
                    
                    # Función helper para limpiar valores
                    def limpiar_valor(val):
                        if val is None:
                            return ''
                        val_str = str(val).strip().strip("'").strip('"').strip()
                        return val_str
                    
                    # Limpiar valores verdes
                    marca = limpiar_valor(marca)
                    modelo = limpiar_valor(modelo)
                    
                    if isinstance(imei, (int, float)):
                        imei = f"{int(imei)}"
                    else:
                        imei = limpiar_valor(imei)
                    
                    serie = limpiar_valor(serie)
                    caja = limpiar_valor(caja)
                    tecnico_responsable = limpiar_valor(tecnico_responsable)
                    
                    # Verificar duplicados
                    if Modem.objects.filter(serie=serie).exists():
                        raise ValueError(f'Modem con SERIE {serie} ya existe en base de datos')
                    
                    # Convertir fechas
                    try:
                        if isinstance(fecha_recepcion, datetime):
                            fecha_recepcion = fecha_recepcion.date()
                        elif hasattr(fecha_recepcion, 'date'):
                            fecha_recepcion = fecha_recepcion.date()
                        elif isinstance(fecha_recepcion, str):
                            from datetime import datetime
                            for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                                try:
                                    fecha_recepcion = datetime.strptime(fecha_recepcion.strip(), fmt).date()
                                    break
                                except:
                                    continue
                    except:
                        fecha_recepcion = None
                    
                    if fecha_entrega:
                        try:
                            if isinstance(fecha_entrega, datetime):
                                fecha_entrega = fecha_entrega.date()
                            elif hasattr(fecha_entrega, 'date'):
                                fecha_entrega = fecha_entrega.date()
                            elif isinstance(fecha_entrega, str):
                                from datetime import datetime
                                for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                                    try:
                                        fecha_entrega = datetime.strptime(fecha_entrega.strip(), fmt).date()
                                        break
                                    except:
                                        continue
                        except:
                            fecha_entrega = None
                    
                    # Buscar cliente
                    cliente_obj = None
                    if cliente_numero:
                        try:
                            cliente_num_str = str(cliente_numero).strip()
                            cliente_obj = Cliente.objects.filter(numero_cliente=cliente_num_str).first()
                            if not cliente_obj:
                                cliente_obj = Cliente.objects.create(
                                    numero_cliente=cliente_num_str,
                                    direccion=f'Cliente {cliente_num_str}',
                                    comuna='Por definir'
                                )
                        except:
                            pass
                    
                    # Buscar medidor
                    medidor_obj = None
                    if medidor_serie:
                        medidor_serie_str = str(medidor_serie).strip()
                        medidor_obj = Medidor.objects.filter(serie=medidor_serie_str).first()
                    
                    # Crear estado por defecto
                    estado_obj = EstadoInventario.objects.filter(nombre='BODEGA').first()
                    if not estado_obj:
                        estado_obj = EstadoInventario.objects.create(nombre='BODEGA')
                    
                    # Crear Modem
                    modem = Modem.objects.create(
                        marca=marca,
                        modelo=modelo,
                        imei=imei if imei else None,
                        serie=serie,
                        fecha_recepcion=fecha_recepcion,
                        fecha_entrega=fecha_entrega,
                        caja=caja,
                        tecnico_responsable=tecnico_responsable,
                        cliente=cliente_obj,
                        medidor=medidor_obj,
                        observaciones=limpiar_valor(observaciones),
                        ip=limpiar_valor(ip),
                        puerto=limpiar_valor(puerto),
                        marca_secundaria=limpiar_valor(marca_secundaria),
                        retirado=limpiar_valor(retirado),
                        serie_secundaria=limpiar_valor(serie_secundaria),
                        irregularidad=limpiar_valor(irregularidad),
                        proyecto=limpiar_valor(proyecto),
                        estado_inventario=estado_obj,
                        ubicacion_actual=bodega
                    )
                    registrar_movimiento_importacion(
                        modem,
                        'MODEM',
                        estado_obj,
                        f'Serie {modem.serie}',
                        idx,
                    )
                
                exitosas += 1
            
            except Exception as e:
                fallidas += 1
                ImportacionExcelError.objects.create(
                    importacion=importacion,
                    numero_fila=idx,
                    motivo=str(e),
                    data_cruda=str(valores)
                )
        
        # Finalizar importación
        importacion.total_filas = contador_filas
        importacion.exitosas = exitosas
        importacion.fallidas = fallidas
        importacion.estado = 'COMPLETADO'
        importacion.observaciones = f'Se importaron {exitosas} de {contador_filas} equipos'
        importacion.save()
    
    except Exception as e:
        importacion.estado = 'ERROR'
        importacion.observaciones = f'Error en importación: {str(e)}'
        importacion.save()
    
    return importacion


def importar_clientes_excel(archivo, usuario):
    """
    Importa clientes desde archivo Excel.
    
    Formato esperado:
    numero_cliente, direccion, comuna, referencia (opcional)
    """
    
    importacion = ImportacionExcel.objects.create(
        tipo='CLIENTES',
        archivo_original=archivo.name if hasattr(archivo, 'name') else 'Upload',
        usuario=usuario,
    )
    
    try:
        wb = openpyxl.load_workbook(archivo)
        ws = wb.active
        
        contador_filas = 0
        exitosas = 0
        fallidas = 0
        
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=False), start=2):
            contador_filas += 1
            
            try:
                valores = [cell.value for cell in row]
                
                if not any(valores):
                    continue
                
                numero, direccion, comuna, referencia = valores[0], valores[1], valores[2], valores[3]
                
                if not all([numero, direccion, comuna]):
                    raise ValueError('Faltan campos: numero_cliente, direccion, comuna')
                
                if Cliente.objects.filter(numero_cliente=numero).exists():
                    raise ValueError(f'Cliente {numero} ya existe')
                
                Cliente.objects.create(
                    numero_cliente=numero,
                    direccion=direccion,
                    comuna=comuna,
                    referencia=referencia or ''
                )
                
                exitosas += 1
            
            except Exception as e:
                fallidas += 1
                ImportacionExcelError.objects.create(
                    importacion=importacion,
                    numero_fila=idx,
                    motivo=str(e),
                    data_cruda=str(valores)
                )
        
        importacion.total_filas = contador_filas
        importacion.exitosas = exitosas
        importacion.fallidas = fallidas
        importacion.estado = 'COMPLETADO'
        importacion.observaciones = f'Se importaron {exitosas} de {contador_filas} clientes'
        importacion.save()
    
    except Exception as e:
        importacion.estado = 'ERROR'
        importacion.observaciones = f'Error: {str(e)}'
        importacion.save()
    
    return importacion


def exportar_equipos_excel(equipos, tipo_equipo='MEDIDORES'):
    """
    Exporta equipos a archivo Excel.
    
    Args:
        equipos: QuerySet de equipos (Medidor, SimCard o Modem)
        tipo_equipo: Tipo de equipo ('MEDIDORES', 'SIM', 'MODEMS')
    
    Returns:
        openpyxl Workbook object
    """
    from openpyxl.styles import Font, PatternFill, Alignment
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = tipo_equipo
    
    # Estilos
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
    # Encabezados según tipo
    if tipo_equipo.upper() == 'MEDIDORES':
        # Debe coincidir con el formato de importación de medidores
        headers = ['#', 'Fecha Recepción', 'Bodega', 'Marca', 'Caja', 'Medidor', 'Módulo', 'Fecha Entrega', 'Entregado A', 'Estado', 'Cliente']
        col_widths = [6, 16, 18, 15, 12, 16, 12, 16, 20, 15, 15]
    elif tipo_equipo.upper() == 'SIM':
        headers = ['IMEI', 'OPERADOR', 'ABONADO', 'DIRECCIÓN IP', 'APN', 'FECHA RECEPCIÓN', 'ENTREGADO A', 'FECHA ENTREGA', 'ESTADO', 'CLIENTE', 'MEDIDOR']
        col_widths = [18, 15, 18, 18, 25, 18, 18, 18, 15, 15, 15]
    elif tipo_equipo.upper() == 'MODEMS':
        headers = ['MARCA', 'MODELO', 'IMEI', 'SERIE', 'Fecha Recepción', 'Fecha Entrega', 'Caja', 'Técnico Responsable', 'Cliente', 'Medidor', 'IP', 'Puerto', 'Marca Secundaria', 'Observaciones', 'Retirado', 'Serie Secundaria', 'Irregularidad', 'Proyecto']
        col_widths = [15, 15, 20, 20, 15, 15, 12, 20, 15, 15, 15, 10, 15, 25, 12, 20, 20, 15]
    else:
        headers = ['Datos']
        col_widths = [20]
    
    # Agregar encabezados
    ws.append(headers)
    
    # Formatear encabezados
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Ajustar ancho de columnas
    for idx, width in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(idx)].width = width
    
    # Agregar datos
    for indice, equipo in enumerate(equipos, start=1):
        if tipo_equipo.upper() == 'MEDIDORES':
            row = [
                indice,
                equipo.fecha_recepcion.strftime('%d-%m-%Y') if equipo.fecha_recepcion else '',
                equipo.bodega or '',
                equipo.marca,
                equipo.caja or '',
                equipo.serie,
                'SI' if getattr(equipo, 'modulo', None) is True else ('NO' if getattr(equipo, 'modulo', None) is False else ''),
                equipo.fecha_entrega.strftime('%d-%m-%Y') if equipo.fecha_entrega else '',
                equipo.entregado_a.nombre_interno if equipo.entregado_a else (equipo.entregado_a_info or ''),
                equipo.estado_inventario.nombre if equipo.estado_inventario else '',
                equipo.cliente.numero_cliente if equipo.cliente else ''
            ]
        elif tipo_equipo.upper() == 'SIM':
            row = [
                equipo.imei or '',
                equipo.operador or '',
                equipo.abonado or '',
                equipo.direccion_ip or '',
                equipo.apn or '',
                equipo.fecha_recepcion.strftime('%d-%m-%Y') if equipo.fecha_recepcion else '',
                equipo.entregado_a_nombre or '',
                equipo.fecha_entrega.strftime('%d-%m-%Y') if equipo.fecha_entrega else '',
                equipo.estado_inventario.nombre if equipo.estado_inventario else '',
                equipo.cliente.numero_cliente if equipo.cliente else '',
                equipo.medidor.serie if equipo.medidor else ''
            ]
        elif tipo_equipo.upper() == 'MODEMS':
            # VERDE: MARCA, MODELO, IMEI, SERIE, Fecha Recepción, Fecha Entrega, Caja, Técnico
            # AMARILLO: Cliente, Medidor
            # NARANJA: IP, Puerto, Marca Sec, Obs, Retirado, Serie Sec, Irregularidad, Proyecto
            row = [
                equipo.marca or '',
                equipo.modelo or '',
                equipo.imei or '',
                equipo.serie,
                equipo.fecha_recepcion.strftime('%d-%m-%Y') if equipo.fecha_recepcion else '',
                equipo.fecha_entrega.strftime('%d-%m-%Y') if equipo.fecha_entrega else '',
                equipo.caja or '',
                equipo.tecnico_responsable or '',
                equipo.cliente.numero_cliente if equipo.cliente else '',
                equipo.medidor.serie if equipo.medidor else '',
                equipo.ip or '',
                equipo.puerto or '',
                equipo.marca_secundaria or '',
                equipo.observaciones or '',
                equipo.retirado or '',
                equipo.serie_secundaria or '',
                equipo.irregularidad or '',
                equipo.proyecto or ''
            ]
        else:
            row = ['']
        
        ws.append(row)
    
    return wb


def generar_plantilla_modem():
    """
    Genera archivo Excel plantilla para importar módems.
    VERDE: Campos del Excel (solo lectura)
    AMARILLO: Campos editables por administrativo
    NARANJA: Campos ocultos (solo admin/auditor)
    """
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font
    from datetime import datetime
    
    wb = Workbook()
    ws = wb.active
    ws.title = 'MODEMS'
    
    # Definir fills
    verde_fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')  # Verde claro
    amarillo_fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')  # Amarillo claro
    naranja_fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')  # Naranja/rosa
    bold_font = Font(bold=True)
    
    # Encabezados
    # VERDE (columnas A-H): MARCA, MODELO, IMEI, SERIE, Fecha Recepción, Fecha Entrega, Caja, Técnico
    verde_headers = ['MARCA', 'MODELO', 'IMEI', 'SERIE', 'Fecha Recepción', 'Fecha Entrega', 'Caja', 'Técnico Responsable']
    
    # AMARILLO (columnas I-J): Cliente, Medidor
    amarillo_headers = ['Cliente', 'Medidor']
    
    # NARANJA (columnas K-R): IP, Puerto, Marca Sec, Observaciones, Retirado, Serie Sec, Irregularidad, Proyecto
    naranja_headers = ['IP', 'Puerto', 'Marca Secundaria', 'Observaciones', 'Retirado', 'Serie Secundaria', 'Irregularidad', 'Proyecto']
    
    col_idx = 1
    
    # Escribir encabezados verdes
    for header in verde_headers:
        cell = ws.cell(row=1, column=col_idx)
        cell.value = header
        cell.fill = verde_fill
        cell.font = bold_font
        col_idx += 1
    
    # Escribir encabezados amarillos
    for header in amarillo_headers:
        cell = ws.cell(row=1, column=col_idx)
        cell.value = header
        cell.fill = amarillo_fill
        cell.font = bold_font
        col_idx += 1
    
    # Escribir encabezados naranjas
    for header in naranja_headers:
        cell = ws.cell(row=1, column=col_idx)
        cell.value = header
        cell.fill = naranja_fill
        cell.font = bold_font
        col_idx += 1
    
    # Ajustar anchos de columna
    ws.column_dimensions['A'].width = 15  # MARCA
    ws.column_dimensions['B'].width = 15  # MODELO
    ws.column_dimensions['C'].width = 20  # IMEI
    ws.column_dimensions['D'].width = 20  # SERIE
    ws.column_dimensions['E'].width = 15  # Fecha Recepción
    ws.column_dimensions['F'].width = 15  # Fecha Entrega
    ws.column_dimensions['G'].width = 12  # Caja
    ws.column_dimensions['H'].width = 20  # Técnico
    ws.column_dimensions['I'].width = 15  # Cliente
    ws.column_dimensions['J'].width = 15  # Medidor
    ws.column_dimensions['K'].width = 15  # IP
    ws.column_dimensions['L'].width = 10  # Puerto
    ws.column_dimensions['M'].width = 15  # Marca Sec
    ws.column_dimensions['N'].width = 25  # Observaciones
    ws.column_dimensions['O'].width = 12  # Retirado
    ws.column_dimensions['P'].width = 20  # Serie Sec
    ws.column_dimensions['Q'].width = 20  # Irregularidad
    ws.column_dimensions['R'].width = 15  # Proyecto
    
    # Hoja de instrucciones
    ws_instruc = wb.create_sheet('Instrucciones')
    ws_instruc['A1'] = 'INSTRUCCIONES PARA IMPORTAR MÓDEMS'
    ws_instruc['A1'].font = Font(bold=True, size=14)
    
    instrucciones = [
        '',
        '1. CAMPOS VERDES (Columnas A-H): Datos que vienen del Excel',
        '   - MARCA: Marca del módem (obligatorio)',
        '   - MODELO: Modelo del módem',
        '   - IMEI: Código IMEI único',
        '   - SERIE: Número de serie único (obligatorio)',
        '   - Fecha Recepción: Fecha de recepción del equipo (DD-MM-YYYY)',
        '   - Fecha Entrega: Fecha de entrega al técnico (DD-MM-YYYY)',
        '   - Caja: Número de caja',
        '   - Técnico Responsable: Nombre del técnico',
        '',
        '2. CAMPOS AMARILLOS (Columnas I-K): Editables por administrativo',
        '   - Cliente: Número de cliente',
        '   - Cliente: Número de cliente',
        '   - Medidor: Serie del medidor',
        '',
        '3. CAMPOS NARANJAS (Columnas K-R): Ocultos para administrativo',
        '   - Solo visibles para admin/auditor',
        '   - Incluyen: IP, Puerto, Marca Secundaria, Observaciones, Retirado, Serie Secundaria, Irregularidad, Proyecto',
        '',
        '4. Notas importantes:',
        '   - Los campos MARCA y SERIE son obligatorios',
        '   - La SERIE debe ser única en el sistema',
        '   - Las fechas deben estar en formato DD-MM-YYYY',
        '   - Los campos amarillos pueden dejarse vacíos y llenarse después en el sistema',
        '   - Los campos naranjas son opcionales y solo para uso administrativo interno',
        '',
        f'Plantilla generada el {datetime.now().strftime("%d-%m-%Y %H:%M")}'
    ]
    
    for idx, instruccion in enumerate(instrucciones, start=2):
        ws_instruc[f'A{idx}'] = instruccion
    
    ws_instruc.column_dimensions['A'].width = 100
    
    # Guardar
    from io import BytesIO
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def generar_plantilla_simcard():
    """
    Genera plantilla Excel para importar SIM Cards
    
    CAMPOS AMARILLOS (obligatorios - vienen desde planilla):
    - IMEI, OPERADOR, ABONADO, DIRECCIÓN IP, APN, FECHA DE RECEPCIÓN, ENTREGADO A
    
    CAMPOS VERDES (opcionales - modifica administrativo después):
    - FECHA ENTREGA, ESTADO, CLIENTE, MEDIDOR
    """
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    
    wb = Workbook()
    ws = wb.active
    ws.title = "SIM Cards"
    
    # Estilos
    amarillo = "FFFF00"
    verde = "00B050"
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
    amarillo_fill = PatternFill(start_color=amarillo, end_color=amarillo, fill_type="solid")
    verde_fill = PatternFill(start_color=verde, end_color=verde, fill_type="solid")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    
    center_alignment = Alignment(horizontal="center", vertical="center")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Encabezados - según imagen del usuario
    headers = [
        ('IMEI', amarillo),
        ('OPERADOR', amarillo),
        ('ABONADO', amarillo),
        ('DIRECCIÓN IP', amarillo),
        ('APN', amarillo),
        ('FECHA DE RECEPCIÓN', amarillo),
        ('ENTREGADO A', amarillo),
        ('FECHA ENTREGA', verde),
        ('ESTADO', verde),
        ('CLIENTE', verde),
        ('MEDIDOR', verde)
    ]
    
    # Agregar encabezados
    for idx, (header, color) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=idx, value=header)
        cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        cell.font = Font(bold=True, size=11)
        cell.alignment = center_alignment
        cell.border = border
    
    # Filas de ejemplo (vacías)
    for row_num in range(2, 12):  # 10 filas de ejemplo
        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=row_num, column=col_num)
            cell.border = border
            if col_num <= 7:  # Campos amarillos (columnas 1-7)
                cell.fill = PatternFill(start_color="FFFF99", end_color="FFFF99", fill_type="solid")
            else:  # Campos verdes (columnas 8-11)
                cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    
    # Ajustar ancho de columnas
    widths = [18, 15, 18, 18, 25, 20, 18, 18, 15, 15, 15]
    for idx, width in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(idx)].width = width
    
    # Agregar hoja de instrucciones
    ws_instruc = wb.create_sheet("Instrucciones")
    
    instrucciones = [
        ("GUÍA DE IMPORTACIÓN SIM CARDS", ""),
        ("", ""),
        ("CAMPOS AMARILLOS (Obligatorios - Debe venir en la planilla):", ""),
        ("IMEI", "Identificador único del equipo/modem (ej: 895601000013094)"),
        ("OPERADOR", "Operador telefónico (ENTEL, CLARO, MOVISTAR, VTECH, etc.)"),
        ("ABONADO", "Número de abonado o identificador del operador"),
        ("DIRECCIÓN IP", "Dirección IP asignada por el operador"),
        ("APN", "Access Point Name configurado (ej: Eneldx.entel.cl)"),
        ("FECHA DE RECEPCIÓN", "Fecha de recepción en bodega (formato: DD-MM-YYYY o Excel date)"),
        ("ENTREGADO A", "Nombre de la persona a quien se entregó (ej: S. Suazo, C. Suazo)"),
        ("", ""),
        ("CAMPOS VERDES (Opcionales - Administrativo completa después):", ""),
        ("FECHA ENTREGA", "Fecha exacta de entrega (se completa después de importar)"),
        ("ESTADO", "Estado del inventario: Instalado, Bodega, Retirado, etc."),
        ("CLIENTE", "Cliente al que está asignada la SIM (se asigna después)"),
        ("MEDIDOR", "Número de medidor asociado (se asigna después)"),
        ("", ""),
        ("NOTAS IMPORTANTES:", ""),
        ("1.", "IMEI debe ser único (no puede haber duplicados)"),
        ("2.", "Los campos amarillos se cargan desde la planilla original"),
        ("3.", "Los campos verdes se modifican usando el botón 'Modificar' en el sistema"),
        ("4.", "Todas las SIM se crean con ESTADO='Instalado' por defecto"),
        ("5.", "Use DD-MM-YYYY o formato de fecha de Excel para fechas"),
        ("6.", "Las columnas verdes pueden dejarse vacías al importar"),
    ]
    
    for row_num, (col1, col2) in enumerate(instrucciones, 1):
        ws_instruc.cell(row=row_num, column=1, value=col1)
        ws_instruc.cell(row=row_num, column=2, value=col2)
        if "GUÍA" in col1:
            ws_instruc.cell(row=row_num, column=1).font = Font(bold=True, size=14)
    
    ws_instruc.column_dimensions['A'].width = 30
    ws_instruc.column_dimensions['B'].width = 70
    
    return wb
