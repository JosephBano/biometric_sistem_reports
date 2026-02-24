# Plan de Diseño e Implementación
## Generador de Informes Biométricos — RRHH ISTPET

---

## Contexto actual

El script `script.py` ya funciona desde línea de comandos: recibe un `.xlsx`, analiza marcaciones biométricas y genera un PDF organizado **por día**. El plan extiende eso con dos cosas:

1. **Nueva vista de reporte: "Por persona"** — en lugar de ver el mes día por día, ver persona por persona con todas sus marcaciones y observaciones.
2. **Interfaz web simple** — una sola página en Flask para subir el archivo y descargar el PDF, sin necesidad de usar la terminal.

---

## Parte 1 — Modificación del Script (`script.py`)

Se añaden las funciones necesarias sin romper el comportamiento actual.

### 1.1 Nueva función de análisis por persona

```
analizar_por_persona(registros, config) → dict
```

Estructura de salida por persona:

```python
{
  "NOMBRE PERSONA": {
    "dias": [
      {
        "fecha": date,
        "llegada": "07:58",        # None si no hay registro
        "salida": "17:00",         # None si no hay registro
        "almuerzo_duracion": 65,   # None si no aplica
        "almuerzo_exceso": 5,      # None si no aplica
        "observaciones": ["Tardanza leve", "Exceso almuerzo"],
        "estado": "ok"             # "ok" | "leve" | "severa" | "incompleto"
      },
      # ... un dict por cada día del mes
    ],
    "resumen": {
      "total_dias": 22,
      "tardanza_leve": 3,
      "tardanza_severa": 1,
      "almuerzo_largo": 2,
      "incompletos": 0
    }
  }
}
```

### 1.2 Nuevo generador de PDF por persona

```
generar_pdf_persona(ruta_salida, analisis_persona, config, nombre_archivo_origen)
```

Estructura del PDF generado:

- **Portada** (igual al reporte general)
- **Resumen general** — tabla con columnas: `Persona | Tard. Leves | Tard. Severas | Exceso Almuerzo | Incompletos`
- **Sección por cada persona**:
  - Encabezado con nombre completo
  - Tabla con columnas: `Día | Llegada | Salida | Dur. Almuerzo | Observaciones`
  - Filas coloreadas según gravedad:
    - Verde → sin novedades
    - Amarillo → tardanza leve o exceso de almuerzo
    - Rojo → tardanza severa
    - Gris → registro incompleto o anómalo

### 1.3 Nuevo argumento CLI

```bash
# Reporte general por día (comportamiento actual, sin cambios)
python script.py archivo.xlsx

# Reporte por persona — todas las personas
python script.py archivo.xlsx --modo persona

# Reporte por persona — una persona específica
python script.py archivo.xlsx --modo persona --persona "Juan Perez"
```

El argumento `--modo` acepta `general` (default) o `persona`.

---

## Parte 2 — Interfaz Web con Flask (`app.py`)

### 2.1 Estructura de archivos resultante

```
script_informe_asistencia/
├── script.py           ← modificado (añade funciones de análisis por persona)
├── app.py              ← nuevo (servidor Flask)
├── templates/
│   └── index.html      ← nuevo (UI de una sola página)
├── uploads/            ← carpeta temporal (creada automáticamente)
├── reports/            ← carpeta temporal (creada automáticamente)
└── requirements.txt    ← actualizado (añade Flask)
```

### 2.2 Flujo de usuario

```
1. Abre la página → localhost:5000
         ↓
2. Arrastra o selecciona el archivo .xlsx
         ↓
3. El backend lee el archivo y devuelve la lista de personas detectadas
         ↓
4. Aparecen las opciones de configuración:
   - Tipo de reporte: [General] [Por persona]
   - Si "Por persona": selector de personas (todas o elegir una)
   - Configuración avanzada (colapsable):
       · Tardanza leve    (default: 08:00)
       · Tardanza severa  (default: 08:05)
       · Almuerzo máximo  (default: 60 min)
       · Personas a excluir
         ↓
5. Click "Generar Reporte" → aparece spinner de carga
         ↓
6. El PDF se descarga automáticamente en el navegador
```

### 2.3 Endpoints de la API Flask

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/` | Sirve la página HTML |
| `POST` | `/subir` | Recibe el `.xlsx`, lo guarda temporalmente, devuelve lista de personas (JSON) |
| `POST` | `/generar` | Recibe opciones + referencia al archivo subido, genera y devuelve el PDF |

### 2.4 Diseño de la UI (una sola página)

La página usa **Bootstrap 5 desde CDN** — sin instalación adicional, sin Node.js, todo en un único `index.html`.

```
┌──────────────────────────────────────────────────────────┐
│         GENERADOR DE INFORMES BIOMÉTRICOS                │
│                  Sistema RRHH · ISTPET                   │
├──────────────────────────────────────────────────────────┤
│                                                          │
│   [ Arrastre su archivo aquí o haga click ]              │
│            .xls / .xlsx aceptados                        │
│                                                          │
│   ── Tipo de reporte ──────────────────────────────      │
│   ○ General (todos los días)                             │
│   ○ Por persona                                          │
│        └── Persona: [ Todas ▾ ]                          │
│                                                          │
│   ▸ Configuración avanzada                               │
│                                                          │
│            [ Generar Reporte PDF ]                       │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## Parte 3 — Consideraciones técnicas

| Punto | Decisión |
|-------|----------|
| Framework web | **Flask** — ligero, sin dependencias pesadas, fácil de ejecutar con `python app.py` |
| Frontend | **HTML + Bootstrap 5 CDN** — sin build steps, sin Node.js |
| Archivos temporales | Se limpian automáticamente después de entregar el PDF (o con TTL de 10 min) |
| Concurrencia | Un usuario a la vez es suficiente para uso interno de RRHH |
| Cómo iniciar | `python app.py` abre en `localhost:5000` |
| Dependencias nuevas | Solo `Flask` (ya tienen `reportlab` y `openpyxl`) |

---

## Orden de implementación

1. Añadir `analizar_por_persona()` al script
2. Añadir `generar_pdf_persona()` al script
3. Añadir el argumento `--modo` al CLI del script
4. Crear `app.py` con Flask y los tres endpoints
5. Crear `templates/index.html`
6. Actualizar `requirements.txt`
7. Prueba completa con el archivo real `REPORTEBIOMETRICOENERO2026.xlsx`
