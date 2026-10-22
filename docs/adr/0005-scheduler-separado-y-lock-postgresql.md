---
title: "ADR-0005 — Separar scheduler y proteger sus corridas con locks PostgreSQL"
tags: [adr, scheduler, gunicorn, postgres]
status: accepted
created: 2026-10-22
updated: 2026-10-22
deciders: [equipo]
supersedes: []
superseded_by: []
related: ["[[ADR-0001-modularizacion-monolito-flask]]", "[[ADR-0002-sync-observable-y-backups]]", "[[ARQUITECTURA]]"]
---

# ADR 0005 — Separar scheduler y proteger sus corridas con locks PostgreSQL

## Contexto y problema

`create_app()` iniciaba el scheduler dentro de cada worker Gunicorn. Con más de
un worker, cada proceso creaba su propio plan en memoria y podía duplicar las
sincronizaciones y los backups. El historial de `public.scheduler_runs` ya es
compartido, pero la ejecución no tenía un líder distribuido.

## Drivers de decisión

1. Permitir escalar Gunicorn sin duplicar jobs programados.
2. Mantener las corridas visibles en `public.scheduler_runs`.
3. Evitar sumar Redis, Celery u otra infraestructura externa.
4. Recuperar automáticamente el liderazgo cuando el proceso scheduler termina.

## Opciones consideradas

- **Proceso scheduler dedicado más advisory locks de PostgreSQL (elegida):** un
  servicio ejecuta `python -m app.scheduler_main`; PostgreSQL elige un líder y
  cada tipo de job tiene su propio lock. No requiere migración de esquema.
- **Scheduler en cada worker con lock por ejecución:** reduce duplicados, pero
  mantiene trabajo de scheduler y threads dentro de los procesos web.
- **Celery/RQ más Redis:** escala colas distribuidas, a costa de nueva
  infraestructura y operación.

## Decisión

Compose mantiene `SYNC_AUTO` como flag de habilitación y usa
`SCHEDULER_PROCESS` para que solo `biometrico-scheduler` inicie el scheduler.
Gunicorn corre con dos workers por defecto y puede configurarse con
`WEB_CONCURRENCY`.

El servicio scheduler obtiene un `pg_try_advisory_lock` de sesión como lock
líder y conserva abierta esa conexión durante la vida del proceso. Si otra
instancia ya es líder, espera y reintenta. Cada job obtiene además un lock
PostgreSQL propio antes de ejecutar; si no puede obtenerlo, registra el evento y
omite esa ejecución. Las conexiones se cierran y liberan explícitamente al
terminar.

El endpoint `/api/scheduler/estado` consulta el lock de liderazgo desde el
proceso web y continúa leyendo el historial desde `public.scheduler_runs`.
`proxima_corrida` sigue siendo local al proceso donde se cargó `schedule`, por
lo que el endpoint web puede devolver `null` para ese campo.

## Consecuencias

- Los workers web no inicializan ni duplican los jobs programados.
- Escalar el número de procesos `biometrico-scheduler` no duplica corridas.
- PostgreSQL debe estar disponible para iniciar jobs; ante fallos, el proceso
  reintenta y no corre jobs sin lock.
- El estado en vivo de una sincronización manual sigue residiendo en `_jobs`
  dentro del worker web que la inició.
- La nueva configuración Docker incluye el proceso scheduler incluso cuando
  `SYNC_AUTO=false`; en ese caso queda inactivo hasta habilitar la variable.

## Validación

- La configuración Compose define workers web sin runner y un servicio scheduler
  separado que comparte `.env`, red y volumen de backups.
- Las corridas automáticas conservan su registro en `public.scheduler_runs`.
- El proceso scheduler verifica el lock líder y cada job usa un lock distinto.

## Seguimientos

- Si se necesita progreso de sync manual compartido entre workers, migrar `_jobs`
  a estado persistido o a un backend compartido en un issue separado.
- Mantener Celery/RQ como alternativa si se necesita una cola de tareas.
