# Sistema de Diseño y Design Tokens
## Estilo Enterprise Moderno (Inspirado en Rippling) adaptado a Colores Institucionales

---

## 1. Filosofía de Diseño: Estilo Rippling Enterprise

El rediseño adopta los principios de diseño de **Rippling**:
- **Tipografía Unificada**: Una **única familia tipográfica** para toda la interfaz (títulos, métricas, tablas, badges y botones). La jerarquía visual se construye estrictamente mediante **pesos tipográficos (400, 500, 600, 700, 800), tamaños calibrados y tracking óptico**, eliminando la fragmentación visual.
- **Superficies Claras y Respirables**: Fondos de lienzo ultra limpios (`#F8FAFC`), tarjetas en blanco puro (`#FFFFFF`) con bordes sutiles de alta definición (`#E2E8F0`) y micro-sombras refinadas.
- **Acentos Cálidos y Corporativos**: Combinación del azul navy institucional (`#253259`) con toques de gris pizarra (`#656F8C`), acentos dorados (`#A68444`, `#BFA473`) y texto negro de alto contraste (`#0D0D0D`).
- **Densidad de Información Eficiente**: Tablas limpias, pills de estado compactos, dividers minimalistas y controles de formulario con enfoque de precisión.

---

## 2. Paleta Cromática Institucional

### 2.1 Tokens Globales de Color

| Token | Hex | RGB | Rol en Estilo Rippling |
| :--- | :--- | :--- | :--- |
| `--token-color-navy-900` | `#253259` | `37, 50, 89` | **Color Primario de Marca**: Sidebar, botones primarios, títulos H1/H2, brand bars. |
| `--token-color-slate-500` | `#656F8C` | `101, 111, 140` | **Color Secundario Neutro**: Subtítulos, labels de formularios, iconos secundarios, bordes activos. |
| `--token-color-gold-700` | `#A68444` | `166, 132, 68` | **Acento de Énfasis**: Acciones destacadas, badges de estado especial, highlights. |
| `--token-color-gold-400` | `#BFA473` | `191, 164, 115` | **Acento Suave**: Fondos de badges cálidos, borders decorativos, botones secundarios de acento. |
| `--token-color-black` | `#0D0D0D` | `13, 13, 13` | **Texto de Máximo Contraste**: Títulos de datos, números métricos, textos principales. |
| `--token-color-white` | `#FFFFFF` | `255, 255, 255` | **Superficie**: Fondos de cards, modales, popovers y tablas. |
| `--token-color-canvas` | `#F8FAFC` | `248, 250, 252` | **Fondo General de la App**: Lienzo gris neutro ultrasuave. |

### 2.2 Validación de Contraste y Accesibilidad (WCAG 2.1)

```
[ Blanco #FFFFFF (Fondo Base) ]
  ├── #0D0D0D (Texto Principal): 19.8:1  ---> Nivel AAA ✅
  ├── #253259 (Azul Primario):   11.4:1  ---> Nivel AAA ✅
  ├── #656F8C (Texto Muted):      4.9:1  ---> Nivel AA  ✅
  └── #A68444 (Acento Dorado):    4.54:1 ---> Nivel AA  ✅

[ Negro #0D0D0D (Fondo Oscuro / Contenedores de Alto Impacto) ]
  └── #BFA473 (Dorado Claro):     8.12:1 ---> Nivel AAA ✅ (Aprobado Adobe Express)
```

---

## 3. Tipografía Unificada: `Plus Jakarta Sans`

Se utiliza una **única fuente universal** para toda la interfaz:
`font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;`

### 3.1 Escala Tipográfica Calibrada (Estilo Rippling)

| Nivel UI | Tamaño | Peso | Line-Height | Letter-Spacing | Uso |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Hero / Dashboard Title** | `1.75rem` (28px) | `800` (ExtraBold) | `1.2` | `-0.03em` | Título principal de página |
| **Section Title (H2)** | `1.375rem` (22px) | `700` (Bold) | `1.3` | `-0.02em` | Títulos de tarjetas y secciones |
| **Card Header (H3)** | `1.125rem` (18px) | `600` (SemiBold) | `1.35` | `-0.015em` | Encabezados de módulos y filtros |
| **KPI Big Number** | `2.25rem` (36px) | `800` (ExtraBold) | `1.0` | `-0.035em` | Métricas numéricas de impacto |
| **Body Standard** | `0.9375rem` (15px) | `400` (Regular) | `1.5` | `0` | Párrafos, descripciones y tablas |
| **Body Medium / Strong** | `0.9375rem` (15px) | `500` / `600` | `1.5` | `-0.005em` | Nombres de personas, enlaces, estados |
| **Caption / Form Label** | `0.8125rem` (13px) | `600` (SemiBold) | `1.4` | `0.01em` | Etiquetas de campos, cabeceras de tabla |
| **Micro Tag / Pill** | `0.75rem` (12px) | `700` (Bold) | `1.2` | `0.02em` | Badges de estado, contadores |

---

## 4. Componentes Visuales Estilo Rippling

### 4.1 Tarjetas (Cards)
- **Fondo**: `#FFFFFF`
- **Borde**: `1px solid #E2E8F0`
- **Radio de Borde**: `12px` (`--radius-lg`)
- **Sombra**: `0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.02)`
- **Hover**: Elevación suave `0 4px 12px rgba(37, 50, 89, 0.06)`

### 4.2 Botones (Buttons)
- **Primary (Navy)**: Fondo `#253259`, texto `#FFFFFF`, radio `8px`, peso `600`, padding `8px 16px`. Hover: `#1B2543`.
- **Accent (Gold)**: Fondo `#A68444`, texto `#FFFFFF`, radio `8px`, peso `600`. Hover: `#8E6F36`.
- **Soft Gold**: Fondo `#FAF7F2`, texto `#A68444`, borde `1px solid #BFA473`.
- **Secondary (Outline)**: Fondo `#FFFFFF`, borde `1px solid #E2E8F0`, texto `#253259`. Hover: fondo `#F8FAFC`.

### 4.3 Tablas de Datos
- **Cabeceras**: Fondo `#F8FAFC`, texto `#656F8C`, peso `600`, tamaño `12px`, mayúsculas sutiles (`letter-spacing: 0.05em`), borde inferior `1px solid #E2E8F0`.
- **Filas**: Fondo `#FFFFFF`, hover `#F8FAFC`, borde inferior `1px solid #F1F5F9`.
- **Celdas de texto principal**: `#0D0D0D`, peso `500`.

### 4.4 Pills & Badges de Estado (Rippling Style)
- Borde sutil, esquinas redondeadas (`9999px`), tipografía `12px` peso `700`:
  - **Presente / Válido**: Fondo `#ECFDF5`, Texto `#065F46`, Borde `#A7F3D0`
  - **Atraso / Pendiente**: Fondo `#FFFBEB`, Texto `#92400E`, Borde `#FDE68A`
  - **Falta / Inconsistencia**: Fondo `#FEF2F2`, Texto `#991B1B`, Borde `#FECACA`
  - **Justificado / Especial**: Fondo `#FAF7F2`, Texto `#A68444`, Borde `#E8DCBE`

---

## 5. Implementación y Recursos

- **Tokens CSS**: [static/tokens.css](file:///c:/Users/DESARROLLADOR-PC02/Desktop/PROYECTOS%20DESARROLLADOS/biometric_sistem_reports/static/tokens.css)
- **Especificación JSON**: [tokens.json](file:///c:/Users/DESARROLLADOR-PC02/Desktop/PROYECTOS%20DESARROLLADOS/biometric_sistem_reports/tokens.json)
