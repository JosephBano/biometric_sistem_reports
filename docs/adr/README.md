---
title: Índice de ADRs — Decisiones Arquitectónicas
tags: [adr, indice, documentacion]
status: active
created: 2026-07-01
updated: 2026-07-27
authors: [documenter]
related: ["[[ARQUITECTURA]]", "[[ADR-0000-use-markdown-for-adrs]]", "[[ADR-0001-modularizacion-monolito-flask]]", "[[ADR-0002-sync-observable-y-backups]]", "[[ADR-0003-horarios-por-rol-funcional]]"]
---

# Architectural Decision Records (ADRs)

Este directorio contiene los **Architecture Decision Records** del proyecto `biometric_sistem_reports`. Cada ADR documenta una decisión arquitectónica significativa: el **contexto** que la motivó, las **alternativas evaluadas**, la **decisión tomada** y sus **consecuencias**.

Los ADRs son inmutables una vez aceptados. Si una decisión se reemplaza por otra, se marca el ADR anterior como `superseded` y se enlaza el nuevo.

---

## Convención usada

Se adopta **MADR ligero en español**, ver [[ADR-0000-use-markdown-for-adrs]] para el detalle de la plantilla y la justificación.

Cada ADR:

- Vive en `docs/adr/`
- Se nombra `NNNN-titulo-en-kebab-case.md`
- Numera secuencialmente (4 dígitos, zero-padded)
- Tiene **frontmatter YAML** Obsidian-compatible
- Tiene wikilinks a docs y ADRs relacionados
- Está escrito en presente indicativo ("Se adopta…", "Se reemplaza…")

---

## Índice de ADRs

| # | Título | Status | Fecha | Resumen |
|---|---|---|---|---|
| [0000](./0000-use-markdown-for-adrs.md) | Adoptar MADR ligero en Markdown para ADRs | accepted | 2026-07-01 | Plantilla y convención de nombrado, estados y formato de los ADRs. |
| [0001](./0001-modularizacion-monolito-flask.md) | Modularización del monolito Flask en Application Factory + Blueprints por dominio | proposed | 2026-07-01 | Migrar `app.py` (2 512 líneas, 81 rutas) a `app/` con Application Factory + Blueprints + servicios en `app/domain/*`. Ver [[ARQUITECTURA]]. |
| [0002](./0002-sync-observable-y-backups.md) | Sync automática observable + Backups portables | accepted | 2026-07-02 | Reforzar scheduler in-process con `public.scheduler_runs` + backups `pg_dump -Fc` con retención. |
| [0003](./0003-horarios-por-rol-funcional.md) | Horarios por grupo funcional con override individual, precedencia explícita y compatibilidad hacia atrás | proposed | 2026-07-27 | Introduce `grupos_funcionales` + `persona_grupos_funcionales` + `horarios_default_grupo` + `overrides_horario_persona` con feature flag por tenant. Distingue explícitamente `tenant.grupos` (operativo) del nuevo `tenant.grupos_funcionales` (laboral). El nombre del archivo conserva el histórico (no es "rol funcional"); ver nota de nomenclatura al inicio del ADR. |

---

## Estados posibles

| Estado | Significado |
|---|---|
| `proposed` | Decisión propuesta, en discusión. Aún no implementada. |
| `accepted` | Decisión aceptada por el equipo y en proceso o completada. |
| `superseded` | Reemplazada por un ADR posterior (enlazar al sucesor). |
| `deprecated` | Decisión que se abandonó o cuya premisa dejó de ser válida. |
| `rejected` | Considerada y descartada (documentada para historia). |

---

## Cómo proponer un nuevo ADR

1. **Asignar número**: revisar este índice; tomar el siguiente correlativo (ej. `0002`).
2. **Copiar la plantilla**: `cp docs/adr/0000-use-markdown-for-adrs.md docs/adr/NNNN-titulo.md`.
3. **Completar todas las secciones**: Context, Decision Drivers, Considered Options, Decision Outcome, Consequences, Validation y Follow-ups. Las secciones vacías se marcan con `_[Pendiente]_`.
4. **Cross-link**: agregar al menos un wikilink a `[[ARQUITECTURA]]` y, si corresponde, a otros ADRs relacionados.
5. **Frontmatter YAML**: completar `title`, `tags`, `status: proposed`, `created`, `authors`.
6. **PR + revisión**: abrir un PR pequeño. La aceptación ocurre durante code review y se refleja cambiando `status: accepted` y haciendo `updated`.
7. **Actualizar este índice** agregando la fila del nuevo ADR con su estado actual.

---

## Cómo se referencian desde el código

Los ADRs son **documentación de decisiones**, no código. No se referencian desde el runtime de la app. Sí se referencian desde:

- Documentación técnica (`docs/*.md`)
- Comentarios en código **solo** cuando el código implementa literalmente la decisión (ej. `# ADR-0001: este decorador se movió a app.domain.rbac`)
- Mensajes de commit y descripciones de PR

---

## Herramientas

Se podría usar `adr-tools` (CLI en Ruby) o `log4brains` (Node). Decidimos **no usarlas** porque:

- La plantilla es muy simple (Markdown + frontmatter)
- El versionado lo cubre git
- Obsidian renderiza los wikilinks nativamente
- Cada ADR tiene su propio número y nombre de archivo, lo que ya es "ADR log"

Si en el futuro se quiere generar un índice HTML/PDF estático, se puede evaluar `mkdocs` + plugin de ADR o un script propio.

---

## Relacionado

- [[ARQUITECTURA]] — Documento principal de arquitectura, fuente de muchas decisiones aquí documentadas.
- [[ADR-0000-use-markdown-for-adrs]] — Plantilla y justificación del formato elegido.
- [[ADR-0001-modularizacion-monolito-flask]] — Primera decisión arquitectónica formal.
