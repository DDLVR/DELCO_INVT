# 🧪 Guía de Testing: Búsqueda de Medidor en Órdenes de Trabajo

## 📋 Preparación

### Requisitos Previos
- [x] Django funcionando (`python manage.py runserver`)
- [x] Base de datos configurada y accesible
- [x] Medidores registrados en la BD
- [x] Usuario técnico logueado

### Verificar Setup
```bash
# En el directorio del proyecto
python manage.py check
# Debe mostrar: "System check identified no issues (0 silenced)."
```

---

## 🚀 Test 1: Verificar API de Búsqueda

### Paso 1: Abrir Terminal/Command Prompt
```bash
cd "C:\Users\DelcoChile TI\Desktop\APPS PROG\DELCO_INVT"
```

### Paso 2: Iniciar Servidor Django
```bash
python manage.py runserver
```

**Esperado:**
```
Starting development server at http://127.0.0.1:8000/
Quit the server with CONTROL-C.
```

### Paso 3: Probar API (en otra terminal)

#### Búsqueda por Serie
```bash
curl "http://localhost:8000/api/buscar-medidores/?q=MED"
```

**Respuesta esperada:**
```json
{
  "results": [
    {
      "id": 1,
      "serie": "MED-2024-001",
      "caja": "001",
      "marca": "Landis+Gyr",
      "custodia": "Técnico Juan",
      "label": "MED-2024-001 - Caja: 001 (Landis+Gyr)"
    }
  ]
}
```

#### Búsqueda por Caja
```bash
curl "http://localhost:8000/api/buscar-medidores/?q=001"
```

#### Búsqueda sin resultados
```bash
curl "http://localhost:8000/api/buscar-medidores/?q=XXXXX"
```

**Respuesta esperada:**
```json
{
  "results": []
}
```

### Paso 4: Obtener Detalles de Medidor
```bash
curl "http://localhost:8000/api/medidores/1/"
```

**Respuesta esperada:**
```json
{
  "id": 1,
  "serie": "MED-2024-001",
  "caja": "001",
  "marca": "Landis+Gyr",
  "modelo": "Modelo X",
  "tipo": "Estándar",
  "en_custodia": "Técnico Juan"
}
```

---

## 🎨 Test 2: Verificar Interfaz de Usuario

### Paso 1: Acceder a Orden de Trabajo
```
http://localhost:8000/ordenes/
```

### Paso 2: Abrir una Orden Existente o Crear Nueva
```
Clic en "Ver Detalle" o "Crear Orden"
```

### Paso 3: Buscar Sección "Registrar/Actualizar Equipos"
- Debe estar visible si la orden está en estado EN_EJECUCION o FINALIZADA
- Debe aparecer solo para técnico responsable

### Paso 4: Probar Campo de Búsqueda de Medidor

#### Prueba A: Búsqueda Básica
1. Haz clic en el campo "📏 Medidor (Serie o Caja)"
2. Escribe "M" (espera 300ms)
3. **Esperado:** No debe mostrar sugerencias (< 2 caracteres)

4. Escribe "MED" 
5. **Esperado:** Debe mostrar dropdown con medidores que contengan "MED"

#### Prueba B: Sugerencias Dinámicas
1. Borra el campo
2. Escribe lentamente: "M", "E", "D"
3. **Esperado:** Las sugerencias se actualizan después de cada tecla (con debounce)

#### Prueba C: Navegación con Teclado
1. El campo debe tener sugerencias visibles
2. Presiona **↓** (flecha abajo)
3. **Esperado:** Primera sugerencia se resalta (gris claro)
4. Presiona **↓** nuevamente
5. **Esperado:** Se mueve a segunda sugerencia
6. Presiona **↑** (flecha arriba)
7. **Esperado:** Vuelve a primera sugerencia
8. Presiona **Enter**
9. **Esperado:** Se selecciona la sugerencia, se cierra dropdown, se llena el campo

#### Prueba D: Selección con Click
1. El campo debe tener sugerencias visibles
2. Haz clic en una sugerencia
3. **Esperado:** Se cierra el dropdown, se llena el campo

#### Prueba E: Información del Medidor
Después de seleccionar un medidor, debe aparecer un recuadro azul con:
```
✓ Medidor seleccionado:
Serie: MED-2024-001
Caja: 001
Marca: Landis+Gyr
En custodia: Bodega Principal
```

### Paso 5: Enviar Formulario
1. Después de seleccionar un medidor
2. Haz clic en botón "Registrar Equipos"
3. **Esperado:** La página se recarga y muestra mensaje de éxito

```
✓ Equipos registrados correctamente en la orden
```

---

## ⚠️ Test 3: Casos de Error

### Caso 1: Medidor sin Custodia del Técnico
**Pasos:**
1. Como técnico, busca un medidor
2. Selecciona uno que NO esté en tu custodia
3. Clic en "Registrar Equipos"

**Esperado:**
```
⚠ El medidor MED-2024-001 no está en tu custodia
```

### Caso 2: Búsqueda Sin Resultados
**Pasos:**
1. Digita "XXXXX" en el campo
2. Espera 300ms

**Esperado:**
```
[No se encontraron medidores]
```

### Caso 3: Error de Red
**Pasos:**
1. Apaga temporalmente el servidor
2. Intenta digitar en el campo de medidor

**Esperado:**
```
[Error en la búsqueda]
```

---

## 🔐 Test 4: Validaciones de Seguridad

### Caso 1: Sin Autenticación
**Pasos:**
1. Logout de la aplicación
2. Intenta acceder a: `http://localhost:8000/api/buscar-medidores/?q=MED`

**Esperado:**
```
Redirect a página de login
O
403 Forbidden
```

### Caso 2: Solo Técnico Responsable
**Pasos:**
1. Como técnico A, crea una orden asignada a técnico B
2. Intenta registrar equipos en esa orden

**Esperado:**
```
❌ Solo el técnico responsable puede registrar equipos
```

### Caso 3: Orden no en Ejecución
**Pasos:**
1. Orden en estado PENDIENTE
2. Intenta registrar equipos

**Esperado:**
```
❌ La orden debe estar en ejecución o finalizada para registrar equipos
```

---

## 📊 Test 5: Performance

### Búsqueda Rápida
**Pasos:**
1. Digita "M"
2. Mira la consola del navegador (F12 → Console)
3. Escribe más rápido: "MED-2024"

**Esperado:**
- La búsqueda NOT se ejecuta en cada tecla (debounce 300ms)
- En consola de red (F12 → Network) debe verse solo 1-2 requests, no 10+

### Resultados Limitados
**Pasos:**
1. Busca un término que tenga muchos medidores
2. Cuanta las sugerencias en el dropdown

**Esperado:**
- Máximo 20 sugerencias mostradas

---

## 📱 Test 6: Compatibilidad Móvil

### En Celular/Tablet
**Pasos:**
1. Accede a `http://[IP_DEL_PC]:8000/ordenes/` desde celular
2. Abre una orden
3. Intenta buscar medidor

**Esperado:**
- Campo responsive (se adapta al tamaño)
- Dropdown se abre bien
- Puedes escribir normalmente
- Las sugerencias son visibles

---

## 🐛 Troubleshooting

### Problema: API retorna 404
**Solución:**
```bash
# Verifica que las rutas están registradas
grep "api_buscar_medidores" web/urls.py

# Verifica que las funciones existen
grep "def api_buscar_medidores" web/views.py
```

### Problema: Dropdown no aparece
**Solución:**
```javascript
// En consola del navegador (F12 → Console)
console.log(document.getElementById('medidor_search'));
// Debe retornar el elemento, no null
```

### Problema: búsqueda muy lenta
**Solución:**
```bash
# Verifica índices en BD
python manage.py sqlmigrate inventario 0001 | grep INDEX

# Agrega índice si falta
python manage.py shell
>>> from inventario.models import Medidor
>>> Medidor._meta.indexes
```

### Problema: CORS Error
**Verificar:**
- API está en mismo dominio (no problema CORS)
- Usar `fetch()` en lugar de jQuery si tienes problemas

---

## ✅ Checklist de Testing

- [ ] API `/api/buscar-medidores/?q=MED` retorna JSON
- [ ] API `/api/medidores/1/` retorna detalles
- [ ] Campo de búsqueda muestra dropdown
- [ ] Puedo escribir y ver sugerencias
- [ ] Puedo navegar con teclado (↑/↓/Enter)
- [ ] Puedo hacer clic en sugerencia
- [ ] Se muestra información del medidor
- [ ] Botón "Registrar Equipos" funciona
- [ ] Mensaje de éxito aparece
- [ ] Error de custodia se muestra correctamente
- [ ] Sin autenticación → Redirect a login
- [ ] Técnico no responsable → Error
- [ ] Orden en estado incorrecto → Error
- [ ] Mobile → Interfaz responsive

---

## 🎉 Resultado Final

Si todos los tests pasaron:

✅ **La implementación está lista para producción**

---

## 📞 Soporte

Si algo falla:

1. **Revisar console del navegador (F12)**
   - Errores JavaScript
   - Errores AJAX/Fetch

2. **Revisar logs de Django**
   - Terminal donde corre `manage.py runserver`

3. **Verificar BD**
   ```bash
   python manage.py dbshell
   SELECT COUNT(*) FROM inventario_medidor WHERE activo=1;
   ```

4. **Limpiar caché del navegador**
   - Ctrl+Shift+Delete (Firefox/Chrome)

---

**Última Actualización:** 2024  
**Status:** ✅ Verificado
