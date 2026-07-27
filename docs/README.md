# Documentación Técnica — Sistema Biométrico RRHH

Este directorio contiene la documentación técnica del sistema, organizada por tema.

## Índice

| Documento | Descripción |
|-----------|-------------|
| **[ARQUITECTURA.md](./ARQUITECTURA.md)** | Arquitectura completa del sistema: capas, Blueprints, servicios de dominio, multi-tenancy, scheduler, riesgos y roadmap de modularización |
| **[ER.md](./ER.md)** | Diagrama ER completo de la base de datos PostgreSQL (schema público + tenant) con todas las tablas, columnas, tipos y relaciones |
| **[SUPERADMIN.md](./SUPERADMIN.md)** | Guía del panel de superadmin: mover usuarios entre tenants, crear y eliminar gestores |
| **[AUTENTICACION.md](./AUTENTICACION.md)** | Sistema de autenticación: login, sesión, bcrypt, CSRF, RBAC, multi-tenant en auth, AES-GCM para credenciales de dispositivos |
| **[API.md](./API.md)** | Referencia completa de las 82 rutas HTTP del sistema (HTML + JSON) con método, decoradores RBAC y descripción |
| **[OPERATIONS.md](./OPERATIONS.md)** | Runbook de operaciones: deploy, variables de entorno críticas, monitoring, troubleshooting común, rollback |
| **[CHANGELOG.md](./CHANGELOG.md)** | Bitácora de cambios del proyecto (estilo Keep a Changelog + wikilinks Obsidian) |
| **[adr/](./adr/README.md)** | Índice de Architectural Decision Records (ADRs). Convención MADR ligero en español. |
| **[superpowers/plans/](./superpowers/plans/)** | Planes de ejecución de tareas grandes (formato superpowers:executing-plans) |

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

Para la arquitectura completa y la propuesta de modularización (Application Factory + Blueprints por dominio), ver [[ARQUITECTURA]] y [[ADR-0001-modularizacion-monolito-flask]].

## Estado del proyecto (post-refactor)

- **Refactor monolito → Application Factory**: cerrado ([[ADR-0001-modularizacion-monolito-flask]] status: completed).
- **Tests**: 271 tests passing (192 unit + 79 integration), cobertura 31.90%.
- **CI**: GitHub Actions con `pgserver` ([[ADR-0004-tests-integracion-pgserver]]).
- **DoD pendientes**: ver "Backlog" en [[ARQUITECTURA]].

## Operaciones y troubleshooting

Para el runbook de operaciones (deploy, monitoring, troubleshooting, rollback), ver [[OPERATIONS]]. Para instalación inicial paso a paso, ver `../DEPLOYMENT.md` (en la raíz del repo).

## Historial de cambios

Para la bitácora completa de versiones, features, refactors y fixes, ver [[CHANGELOG]].
