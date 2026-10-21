# Protocolo de Lanzamiento a Producción: Salvaguarda de Seguridad `FLASK_SECRET_KEY`

- **Issue Asociado:** [#3 — [Seguridad] La app arranca en producción con SECRET_KEY por defecto conocida](https://github.com/JosephBano/biometric_sistem_reports/issues/3)
- **Fecha:** 2026-10-21
- **Responsable:** Alexander Martínez
- **Tipo de Cambio:** Seguridad / Configuración Crítica (Breaking Change preventivo en despliegues mal configurados)

---

## 1. Resumen Ejecutivo

Este documento define el procedimiento obligatorio para el despliegue a producción de la corrección de seguridad del Issue #3.

La aplicación ahora exige estrictamente que la variable de entorno `FLASK_SECRET_KEY` esté definida, no sea la clave por defecto (`dev-secret-change-in-production`) y tenga una longitud mínima de 32 caracteres al inicializarse en entorno `production` (`ProductionConfig`). En caso de incumplir estos criterios, la aplicación abortará inmediatamente su ejecución con un `RuntimeError`.

---

## 2. Pre-condición Crítica (OBLIGATORIO ANTES DEL DEPLOY)

> [!CAUTION]
> Si se despliega este cambio sin haber configurado previamente una `FLASK_SECRET_KEY` válida en el archivo `.env` del servidor de producción, el contenedor de la aplicación **fallará al arrancar** y el servicio quedará inaccesible.

### 2.1 Verificación en el Servidor de Producción

1. Conectarse al servidor donde corre la aplicación en producción.
2. Acceder al directorio del proyecto y verificar la línea `FLASK_SECRET_KEY` en el archivo `.env`:
   ```bash
   grep "^FLASK_SECRET_KEY=" .env
   ```
3. Comprobar que:
   - Exista la variable.
   - No sea `cambiar_esto_por_una_clave_larga_y_segura` ni `dev-secret-change-in-production`.
   - La cadena tenga una longitud de al menos 32 caracteres.

### 2.2 Generación de Clave Criptográfica Segura

Si la variable falta, es insegura o es el valor por defecto, generar una nueva clave ejecutando:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Añadirla o actualizarla en el `.env` de producción:
```ini
FLASK_SECRET_KEY=<cadena_de_64_caracteres_hex_generada>
```

---

## 3. Procedimiento de Lanzamiento Paso a Paso

### Paso 1: Backup Preventivo
Realizar un respaldo de seguridad del estado actual y de la base de datos antes de aplicar el merge:
```bash
docker compose exec db pg_dump -U $POSTGRES_USER $POSTGRES_DB > /data/backups/pre_deploy_secret_key_$(date +%Y%m%d_%H%M%S).sql
```

### Paso 2: Descarga de la Versión Actualizada
En el servidor de producción:
```bash
git fetch origin
git pull --ff-only origin main
```

### Paso 3: Reconstrucción y Despliegue de Contenedores
Reconstruir la imagen de la aplicación para aplicar los cambios de código y reiniciar el servicio:
```bash
docker compose up -d --build biometrico-app
```

### Paso 4: Verificación Inmediata de Logs de Arranque
Monitorear el arranque del contenedor de la aplicación:
```bash
docker compose logs -f --tail=50 biometrico-app
```

**Criterio de éxito en logs:**
- El worker de Gunicorn arranca sin excepciones `RuntimeError`.
- No hay mensaje de fallo de `FLASK_SECRET_KEY`.

---

## 4. Pruebas de Verificación Post-Despliegue (Smoke Tests)

Una vez iniciado el contenedor:
1. **Acceso a la interfaz web:** Abrir el navegador en la URL institucional del sistema (`/biometrico/login`).
2. **Inicio de sesión:** Iniciar sesión con un usuario administrativo.
3. **Validación CSRF:** Probar el envío de un formulario (por ejemplo, consulta de asistencias o navegación entre paneles). Verificar que no retorne error 403 CSRF.
4. **Persistencia de sesión:** Recargar la página y comprobar que la cookie de sesión permanezca válida.

---

## 5. Plan de Rollback (Contingencia)

En caso de fallo imprevisto durante el arranque:

1. **Si el contenedor falla con `RuntimeError: FLASK_SECRET_KEY no configurada o insegura`:**
   - La causa es que el `.env` de producción no tiene la clave o es menor a 32 caracteres.
   - Solución inmediata: Editar `.env`, colocar la clave generada con `secrets.token_hex(32)` y reiniciar con `docker compose restart biometrico-app`.

2. **Reversión de código:**
   Si por alguna razón fuera necesario volver a la versión anterior:
   ```bash
   git checkout HEAD~1
   docker compose up -d --build biometrico-app
   ```
