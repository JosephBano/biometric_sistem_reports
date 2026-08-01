---
title: "ADR-0000 — Adoptar MADR ligero en Markdown para registrar decisiones arquitectónicas"
tags: [adr, plantilla, documentacion, proceso]
status: accepted
created: 2026-07-01
updated: 2026-07-01
deciders: [arquitecto, documenter]
related: ["[[ARQUITECTURA]]", "[[ADR-0001-modularizacion-monolito-flask]]"]
---

# ADR 0000 — Adoptar MADR ligero en Markdown para ADRs

## Context and Problem Statement

El proyecto `biometric_sistem_reports` está entrando en una fase de decisiones arquitectónicas explícitas (ver [[ADR-0001-modularizacion-monolito-flask]]) y necesitamos un mecanismo para:

- Documentar el **porqué** de cada decisión, no solo el **qué**.
- Mantener un histórico inmutable y versionado en git.
- Que sea fácil escribir uno nuevo sin tooling externo.
- Que se renderice correctamente en Obsidian (vault del equipo) y en GitHub.
- Que cualquier dev del equipo pueda proponer un ADR sin curva de aprendizaje.

## Considered Options

### A. MADR ligero en Markdown (elegida)

Plantilla derivada de [MADR](https://adr.github.io/madr/) (~3 000 proyectos OSS la usan), reducida a lo esencial.

- ✅ Texto plano, versionado en git.
- ✅ Renderiza en Obsidian con wikilinks.
- ✅ Sin dependencias de runtime.
- ✅ Plantilla corta y explícita (ver sección "Decision Outcome").
- ❌ No genera índice HTML automáticamente (lo cubre [[README|docs/adr/README]]).
- ❌ No valida formato (lo cubre code review).

### B. `adr-tools` (CLI en Ruby)

Herramienta clásica de la comunidad ADR. Comandos: `adr new`, `adr link`, `adr generate`.

- ✅ Numeración automática.
- ✅ Genera índice HTML/PDF.
- ❌ Requiere Ruby instalado localmente y en CI.
- ❌ No respeta frontmatter YAML para Obsidian.
- ❌ Estructura fija en 4 secciones; menos flexible que MADR.
- ❌ El equipo ISTPET trabaja en Python; añadir Ruby es fricción.

### C. Plantilla Nygard clásica (4 secciones: Context / Decision / Consequences)

La propuesta original de Michael Nygard (`/adr/NNNN-title.md` con 3 secciones).

- ✅ Máxima simplicidad.
- ❌ No captura **alternativas evaluadas** ni **drivers**, solo la decisión final.
- ❌ Insuficiente cuando hay trade-offs (como en [[ADR-0001-modularizacion-monolito-flask]]).

### D. `log4brains` (Node + Next.js)

UI web para ADRs.

- ✅ UI bonita para navegar el histórico.
- ❌ Requiere Node, build pipeline y hosting.
- ❌ Sobre-ingeniería para un proyecto de tamaño medio.
- ❌ No se integra con Obsidian ni con git nativo.

## Decision Drivers

- D1 — Liviano, sin tooling extra más allá de git + editor.
- D2 — Compatible con Obsidian (wikilinks `[[...]]`, frontmatter YAML).
- D3 — Capturar tanto drivers como alternativas y consecuencias.
- D4 — Numerado en orden cronológico, cero rotación de IDs.
- D5 — Mínimo fricción para crear uno nuevo.

## Decision Outcome

**Se adopta la opción A: MADR ligero en Markdown.**

### Estructura esperada de cada ADR

```markdown
---
title: "<título en imperativo>"
tags: [adr]
status: proposed | accepted | superseded | deprecated
created: YYYY-MM-DD
updated: YYYY-MM-DD
deciders: [nombre1, nombre2]
supersedes: []
superseded_by: []
---

# NNNN. <Título>

## Context and Problem Statement
<qué problema motiva la decisión>

## Decision Drivers
<lista numerada de drivers / restricciones / objetivos>

## Considered Options
<lista de alternativas; cada una con ✅ / ❌ y por qué se descartó>

## Decision Outcome
<la decisión en presente indicativo>

## Consequences
- Positivas: ...
- Negativas / costos: ...
- Neutrales: ...
- Riesgos a vigilar: ...

## Implementation Plan
<plan incremental si aplica>

## Validation
<criterios observables que confirman que la decisión se ejecutó correctamente>

## Follow-ups (backlog)
<trabajo futuro derivado>

## Relacionado
<wikilinks a docs y ADRs>
```

### Convención de nombres

`NNNN-titulo-en-kebab-case.md`

- `NNNN` = número secuencial de 4 dígitos, zero-padded (`0000`, `0001`, …).
- `titulo-en-kebab-case` = palabras en minúscula separadas por guión.
- Longitud objetivo: < 60 caracteres.

### Convención de estados

`proposed` → (revisión) → `accepted` → (eventualmente) → `superseded` o `deprecated`.

No se borran ADRs aceptados. Si la decisión se invalida:

- Cambiar `status: superseded` y agregar `superseded_by: ["0005-..."]`.
- Crear el nuevo ADR (el sucesor) que documenta la nueva decisión.

Si la decisión fue correcta en su momento pero ya no aplica:

- Cambiar `status: deprecated` con una nota explicativa en `Consequences`.

Si nunca se implementó y se descarta:

- Cambiar `status: rejected`.

### Ubicación

Todos los ADRs viven en `docs/adr/`. El índice se mantiene en [[README|docs/adr/README]].

### Cross-linking

- Cada ADR enlaza con wikilinks a `[[ARQUITECTURA]]` cuando aplica.
- Cada ADR referencia ADRs relacionados (anteriores o sucesores) en la sección "Relacionado".
- La sección "Considered Options" puede enlazar a otros ADRs que motivaron las alternativas.

### Frontmatter obligatorio

```yaml
---
title: <string>
tags: [adr]
status: <proposed|accepted|superseded|deprecated|rejected>
created: YYYY-MM-DD
updated: YYYY-MM-DD
deciders: [lista de personas o roles]
supersedes: [lista de ADRs anteriores, si aplica]
superseded_by: [lista de ADRs sucesores, si aplica]
related: [lista de wikilinks]
---
```

## Consequences

**Positivas**:

- Cualquier dev puede escribir un ADR siguiendo la plantilla sin más.
- Obsidian renderiza todo (frontmatter, mermaid, wikilinks) sin config.
- El versionado es git puro: cada PR es exactamente un diff de un ADR.
- La sección "Considered Options" preserva historia aunque la decisión cambie.

**Negativas / costos**:

- Renunciamos a la generación automática de índice HTML (hay que mantener el [[README|docs/adr/README]] manualmente).
- Sin validación de formato automática (mitigado con plantillas en Obsidian + code review).
- Si el equipo crece a >10 devs, considerar `adr-tools` o `log4brains` (backlog P3).

**Neutrales**:

- El primer ADR ([[ADR-0000-use-markdown-for-adrs]]) sirve como ejemplo canónico.
- Los ADRs futuros pueden usar secciones extras (ej. "Security Implications", "Cost Analysis") si el caso lo amerita.

## Implementation Plan

1. Crear `docs/adr/` y este ADR (plantilla).
2. Crear [[README|docs/adr/README]] como índice.
3. Documentar cada decisión futura siguiendo la plantilla.

## Validation

- Este ADR existe y está en `status: accepted`.
- [[README|docs/adr/README]] lista todos los ADRs.
- Cualquier ADR nuevo cumple la plantilla (verificación manual en PR).
- Los wikilinks en Obsidian resuelven a archivos existentes.

## Follow-ups (backlog)

- **P3**: evaluar `mkdocs` + plugin ADR si el equipo quiere un sitio estático público.
- **P3**: si crecen > 10 devs, evaluar `adr-tools` para validación de formato.

## Relacionado

- [[ARQUITECTURA]] — El documento de arquitectura del que este ADR es meta-herramienta.
- [[ADR-0001-modularizacion-monolito-flask]] — El primer ADR "real" del proyecto, candidato natural para usar esta plantilla.
