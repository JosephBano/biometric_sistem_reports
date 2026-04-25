# Documentación Técnica — Sistema Biométrico RRHH

Este directorio contiene la documentación técnica del sistema, organizada por tema.

## Índice

| Documento | Descripción |
|-----------|-------------|
| **[ER.md](./ER.md)** | Diagrama ER completo de la base de datos PostgreSQL (schema público + tenant) con todas las tablas, columnas, tipos y relaciones |
| **[SUPERADMIN.md](./SUPERADMIN.md)** | Guía del panel de superadmin: mover usuarios entre tenants, crear y eliminar gestores |
| **[API.md](./API.md)** | Referencia completa de todas las rutas HTTP del sistema (web + API JSON) |
| **[AUTENTICACION.md](./AUTENTICACION.md)** | Sistema de autenticación: login, roles, contraseñas, sesión |

## Generar documentación automáticamente

```bash
# Generar ER.md desde db/schema.py (requiere Python 3.12+)
python docs/generate_er.py

# Verificar sintaxis de todos los archivos de documentación
python docs/generate_er.py --verify-only
```

## Arquitectura rápida

```
public.tenants ←─ public.usuarios  (cada usuario pertenece a un tenant)
       │
       └──[ tenant schema ]──┬─ personas ── asistencia ── justificaciones
                             ├─ grupos ── categorias ── tipos_persona
                             ├─ periodos_vigencia
                             ├─ plantillas_horario ── asignaciones_horario
                             ├─ dispositivos ── sync_log
                             └─ feriados ── breaks_categorizados
```

Para contexto de arquitectura completo, ver `../AGENTS.md` (raíz del proyecto).
