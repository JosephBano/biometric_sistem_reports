# Guía de Despliegue — Sistema Biométrico RRHH ISTPET

Esta guía cubre la instalación, puesta en producción y distribución del sistema en todos los entornos posibles.

| Escenario | Sistema | Docker |
|-----------|---------|--------|
| [A — Escritorio Linux](#escenario-a--escritorio-linux) | Ubuntu / Mint / Fedora (desktop) | Docker Engine |
| [B — Servidor Linux](#escenario-b--servidor-linux) | Ubuntu / Debian (headless) | Docker Engine |
| [C — Windows](#escenario-c--windows) | Windows 10 / 11 | Docker Desktop |
| [D — Sin código fuente](#escenario-d--distribuir-la-imagen-sin-código-fuente) | Cualquier OS | Imagen `.tar` exportada |

En todos los casos el flujo de despliegue y actualización es el mismo una vez que Docker está instalado. Los pasos que difieren se indican en cada escenario.

---

> **Inicio rápido** — Si ya tienes Docker y el `.env` configurado:
> ```bash
> docker compose up -d --build   # primera vez (levanta PostgreSQL + la app)
> docker compose up -d --build   # para aplicar actualizaciones
> docker compose logs -f          # ver qué hace
> ```

---

## Arquitectura de servicios

El sistema corre con **dos contenedores Docker** que se coordinan automáticamente:

| Servicio | Imagen | Función |
|----------|--------|---------|
| `biometrico-db` | `postgres:16-alpine` | Base de datos PostgreSQL. Arranca primero. |
| `biometrico-app` | construida desde `Dockerfile` | Aplicación Flask. Espera a que la DB esté lista (healthcheck). |

Los datos de PostgreSQL se guardan en el volumen nombrado `postgres_data`. Los uploads y reportes PDF se guardan en el volumen `app_data`. **Ambos volúmenes persisten entre reinicios, actualizaciones y `docker compose down`.**

---

## Requisito común a todos los escenarios

La máquina donde corra Docker debe estar en la **misma red local** que el dispositivo ZK biométrico para que la sincronización funcione.

---

---

# ESCENARIO A — Escritorio Linux

Trabajas directamente en la máquina de escritorio. No necesitas SSH.

---

## A1 — Instalar Docker Engine

Abrir una terminal y ejecutar:

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
```

> Estos comandos funcionan en Ubuntu, Linux Mint y cualquier derivado de Ubuntu. Para Fedora / Arch, la instalación varía pero Docker está disponible en sus repositorios oficiales.

Agregar tu usuario al grupo Docker (evita escribir `sudo` en cada comando):

```bash
sudo usermod -aG docker $USER
```

**Importante:** cerrar sesión y volver a entrar para que el cambio de grupo aplique. Luego verificar:

```bash
docker --version
docker compose version
```

---

## A2 — Obtener el código del proyecto

Elige una de estas opciones:

**Si tienes el proyecto en un repositorio Git:**

```bash
cd ~/Documentos
git clone https://github.com/TU_USUARIO/TU_REPO.git rrhh-biometrico
cd rrhh-biometrico
```

**Si tienes el proyecto en una carpeta local:**

```bash
# Simplemente navegar a donde ya está
cd /ruta/al/proyecto/script_informe_asistencia
```

---

## A3 — Configurar el `.env`

```bash
cp .env.example .env
nano .env          # o gedit .env si prefieres editor gráfico
```

Rellenar los valores obligatorios (ver sección [Referencia del .env](#referencia-del-env) al final).

Los valores más importantes en esta instalación son:

- `ZK_IP`, `ZK_PORT`, `ZK_PASSWORD` — datos del dispositivo biométrico
- `POSTGRES_PASSWORD` — contraseña de la base de datos (elegir una segura)
- `FLASK_SECRET_KEY` — clave aleatoria para sesiones Flask
- `NOMBRE_INSTITUCION` — aparece en los encabezados de los PDFs

> La variable `DATABASE_URL` se configura automáticamente en el `docker-compose.yml` para usar el servicio `db` como host. En el `.env` local puedes dejarla apuntando a `localhost:5432` para desarrollo sin Docker.

---

## A4 — Iniciar el sistema

```bash
docker compose up -d --build
```

La primera vez descarga las imágenes base de Python y PostgreSQL, e instala las dependencias: puede tardar 3–5 minutos.

Docker levanta primero el servicio `biometrico-db` y espera a que PostgreSQL esté listo (healthcheck). Recién entonces arranca `biometrico-app`, que al iniciar ejecuta `init_db()` para crear el schema y sembrar datos iniciales.

Verificar que ambos servicios están corriendo:

```bash
docker compose ps
```

La columna `Status` debe decir `Up` para ambos contenedores. Abrir el navegador en:

```
http://localhost:5000
```

---

## A5 — Comportamiento al reiniciar la PC

Ambos contenedores tienen `restart: unless-stopped`. Esto significa:

- Si reinicias la PC: los contenedores **arrancan automáticamente** cuando Docker arranca.
- Docker arranca automáticamente con el sistema en la mayoría de distribuciones Linux tras la instalación.
- Si detuviste los contenedores manualmente con `docker compose down`, **no** arrancarán solos al reiniciar.

Para verificar si Docker arranca con el sistema:

```bash
sudo systemctl is-enabled docker
# Debe responder: enabled
```

Si responde `disabled`, activarlo:

```bash
sudo systemctl enable docker
```

---

---

# ESCENARIO B — Servidor Linux

El servidor corre sin interfaz gráfica. Te conectas por SSH desde tu PC.

---

## B1 — Instalar Docker Engine en el servidor

Conectarse por SSH:

```bash
ssh usuario@IP_DEL_SERVIDOR
```

Ejecutar la misma secuencia de instalación del [paso A1](#a1--instalar-docker-engine), ya que los servidores Ubuntu/Debian son compatibles.

---

## B2 — Subir el código al servidor

**Opción A — Con Git (recomendado):**

```bash
# En el servidor, dentro de la sesión SSH
cd /opt
sudo git clone https://github.com/TU_USUARIO/TU_REPO.git rrhh-biometrico
sudo chown -R $USER:$USER /opt/rrhh-biometrico
cd /opt/rrhh-biometrico
```

**Opción B — Con SCP desde tu PC:**

```bash
# Ejecutar desde tu PC local, NO desde el servidor
scp -r /ruta/local/script_informe_asistencia usuario@IP_SERVIDOR:/opt/rrhh-biometrico
```

Luego en el servidor:

```bash
ssh usuario@IP_SERVIDOR
cd /opt/rrhh-biometrico
```

**Opción C — Comprimir y transferir:**

Desde tu PC:

```bash
tar -czf rrhh.tar.gz \
  --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='venv' --exclude='.venv' --exclude='data/' --exclude='.env' \
  script_informe_asistencia/
scp rrhh.tar.gz usuario@IP_SERVIDOR:/opt/
```

En el servidor:

```bash
cd /opt
tar -xzf rrhh.tar.gz
mv script_informe_asistencia rrhh-biometrico
cd rrhh-biometrico
```

---

## B3 — Configurar el `.env`

```bash
cp .env.example .env
nano .env
```

Rellenar los valores (ver sección [Referencia del .env](#referencia-del-env)).

---

## B4 — Iniciar el sistema

```bash
docker compose up -d --build
```

Verificar ambos servicios:

```bash
docker compose ps
curl http://localhost:5000/estado-sync
```

La app queda accesible para cualquier máquina en la red local en:

```
http://IP_DEL_SERVIDOR:5000
```

---

## B5 — Abrir el firewall (si aplica)

Si el servidor tiene UFW activado, solo es necesario abrir el puerto de la app (PostgreSQL no necesita estar expuesto externamente):

```bash
sudo ufw allow 5000/tcp
sudo ufw status
```

El puerto `5432` de PostgreSQL está mapeado **solo a localhost** (`127.0.0.1:5432`) por diseño — no es accesible desde la red externa.

---

## B6 — Optimización de red para Linux (opcional)

En Linux con Docker Engine, si el dispositivo ZK está en una subred que no es alcanzable por el NAT de Docker, se puede usar `network_mode: host` para la app. **Esta opción es incompatible con `depends_on`** (que coordina el arranque de PostgreSQL).

Para usarla, editar `docker-compose.yml` en el servicio `biometrico-app`:

```yaml
# Comentar el bloque ports y depends_on:
# ports:
#   - "5000:5000"
# depends_on:
#   db:
#     condition: service_healthy

# Descomentar esta línea:
network_mode: host
```

Cuando se usa `network_mode: host`, levantar primero la base de datos por separado:

```bash
docker compose up -d db       # esperar unos segundos a que esté healthy
docker compose up -d biometrico-app
```

**No usar esta opción en Windows ni macOS.**

---

---

# ESCENARIO C — Windows

---

## C1 — Instalar Docker Desktop

1. Descargar Docker Desktop desde [https://docs.docker.com/desktop/install/windows-install/](https://docs.docker.com/desktop/install/windows-install/)

2. Ejecutar el instalador. Durante la instalación:
   - Asegurarse de que la opción **"Use WSL 2 instead of Hyper-V"** esté marcada (recomendado).
   - Si el PC no soporta WSL 2, Docker Desktop usará Hyper-V automáticamente.

3. Reiniciar el PC cuando el instalador lo solicite.

4. Abrir Docker Desktop. La primera vez puede tardar 1–2 minutos en iniciar.

5. Verificar en PowerShell o en la Terminal de Windows:

```powershell
docker --version
docker compose version
```

> **Nota sobre `network_mode: host`:** Docker Desktop para Windows no soporta `network_mode: host` de la misma manera que Linux. El `docker-compose.yml` de este proyecto usa `ports: ["5000:5000"]` como predeterminado, que sí funciona en Windows. No cambiar a `network_mode: host` en Windows.

---

## C2 — Obtener el código

Abrir PowerShell o la Terminal de Windows.

**Con Git:**

```powershell
cd C:\Users\TU_USUARIO\Documentos
git clone https://github.com/TU_USUARIO/TU_REPO.git rrhh-biometrico
cd rrhh-biometrico
```

Si no tienes Git, descargarlo desde [https://git-scm.com](https://git-scm.com).

**Sin Git — copiar la carpeta manualmente:**

Copiar la carpeta del proyecto a cualquier ubicación, por ejemplo `C:\rrhh-biometrico`, y abrir PowerShell en esa carpeta:

```powershell
cd C:\rrhh-biometrico
```

---

## C3 — Configurar el `.env`

En PowerShell:

```powershell
copy .env.example .env
notepad .env
```

Rellenar los valores en el Bloc de notas y guardar (ver sección [Referencia del .env](#referencia-del-env)).

Generar una `FLASK_SECRET_KEY` segura: abrir PowerShell y ejecutar:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Si Python no está instalado en Windows, también se puede generar una clave en [https://www.uuidgenerator.net/](https://www.uuidgenerator.net/) usando un UUID largo como valor.

---

## C4 — Iniciar el sistema

```powershell
docker compose up -d --build
```

La primera vez tarda 3–5 minutos. Cuando termine:

```powershell
docker compose ps
```

Deben aparecer **dos contenedores** en estado `Up`: `biometrico-db` y `biometrico-app`. Abrir el navegador en:

```
http://localhost:5000
```

---

## C5 — Comportamiento al reiniciar Windows

Docker Desktop tiene una opción para arrancar con Windows. Para activarla:

1. Hacer clic derecho en el ícono de Docker en la barra de tareas → **Settings**
2. En la sección **General** → activar **"Start Docker Desktop when you sign in to your computer"**

Ambos contenedores tienen `restart: unless-stopped`, así que cuando Docker Desktop arranque, los contenedores también lo harán automáticamente.

---

## C6 — Conectividad con el dispositivo ZK en Windows

Docker Desktop en Windows usa NAT para la red de los contenedores. Las conexiones salientes del contenedor hacia la red local (donde está el ZK) pasan por la interfaz de red de Windows automáticamente.

Si el contenedor no puede alcanzar el dispositivo ZK:

1. Verificar que Windows puede hacer ping al dispositivo: abrir CMD y ejecutar `ping IP_DEL_ZK`
2. Verificar que el firewall de Windows no está bloqueando Docker.
3. En Docker Desktop → Settings → Resources → Network: verificar que no hay restricciones de red activadas.

---

---

# ESCENARIO D — Distribuir la imagen sin código fuente

Usa este flujo cuando quieres instalar el sistema en otra PC **sin copiar el código fuente** — solo las imágenes Docker compiladas. Es el método más rápido para entregar la aplicación a máquinas de producción que no tienen acceso al repositorio.

---

## D1 — Construir y exportar las imágenes (desde la PC de desarrollo)

Primero asegurarse de que las imágenes están construidas:

```bash
docker compose build --no-cache
```

Luego exportar **ambas imágenes** (la app y PostgreSQL):

```bash
# Imagen de la app (construida localmente)
docker save -o ~/Desktop/rrhh-app.tar script_informe_asistencia-biometrico-app

# Imagen de PostgreSQL (descargada de Docker Hub)
docker save -o ~/Desktop/rrhh-postgres.tar postgres:16-alpine
```

> Los nombres de las imágenes se pueden confirmar con `docker images`.

---

## D2 — Archivos a transferir

Copiar los siguientes archivos a la PC de destino (USB, Google Drive, etc.):

| Archivo | Descripción |
|---|---|
| `rrhh-app.tar` | Imagen Docker de la aplicación Flask |
| `rrhh-postgres.tar` | Imagen Docker de PostgreSQL 16 |
| `docker-compose.yml` | Configuración de ambos contenedores |
| `.env` | Variables de entorno (credenciales ZK, PostgreSQL, etc.) |

Colocarlos todos en la misma carpeta, por ejemplo `C:\rrhh\` en Windows o `/opt/rrhh/` en Linux.

> **Atención con el `.env`:** contiene contraseñas de la BD y el dispositivo ZK. Transferirlo por un medio seguro y no subirlo a repositorios públicos.

---

## D3 — Preparar el `docker-compose.yml` en la PC de destino

En la PC de destino, abrir el `docker-compose.yml` y reemplazar en el servicio `biometrico-app`:

```yaml
build: .
```

por:

```yaml
image: script_informe_asistencia-biometrico-app
```

Esto es necesario porque en la PC de destino no existe el código fuente — solo se usará la imagen ya compilada.

---

## D4 — Cargar las imágenes e iniciar (Linux)

```bash
docker load -i rrhh-postgres.tar
docker load -i rrhh-app.tar
docker compose up -d
```

Verificar:

```bash
docker compose ps
```

Acceder en: `http://localhost:5000`

---

## D5 — Cargar las imágenes e iniciar (Windows)

Abrir PowerShell en la carpeta donde están los archivos:

```powershell
docker load -i rrhh-postgres.tar
docker load -i rrhh-app.tar
docker compose up -d
```

Verificar:

```powershell
docker compose ps
```

Acceder en: `http://localhost:5000`

---

## D6 — Actualizar la aplicación (flujo sin código fuente)

Cuando salga una nueva versión, repetir desde la PC de desarrollo:

```bash
# 1. Reconstruir con los últimos cambios
docker compose build

# 2. Exportar la nueva imagen (solo la app, PostgreSQL no cambia)
docker save -o ~/Desktop/rrhh-app-v2.tar script_informe_asistencia-biometrico-app
```

En la PC de destino:

```bash
# Detener el contenedor de la app (la BD puede seguir corriendo)
docker compose stop biometrico-app

# Cargar la nueva imagen
docker load -i rrhh-app-v2.tar

# Volver a levantar
docker compose up -d
```

> Los datos de PostgreSQL están en el volumen `postgres_data` — **no se pierden** al actualizar la imagen de la app.

---

---

# Primer uso (todos los escenarios)

Una vez que el sistema esté corriendo, estos pasos son iguales sin importar el sistema operativo.

## 1 — Acceder a la aplicación

- **Escritorio o Windows:** abrir el navegador en `http://localhost:5000`
- **Servidor:** abrir `http://IP_DEL_SERVIDOR:5000` desde cualquier PC en la red

Si `APP_PASSWORD_HASH` está configurado en el `.env`, el sistema pedirá contraseña. Si está vacío, no hay autenticación (modo desarrollo).

## 2 — Verificar la base de datos

Al iniciar por primera vez, la app crea automáticamente el schema de PostgreSQL y carga:
- El tenant `istpet` con su sede principal y dispositivo ZK
- Los tipos de persona: `Empleado` y `Practicante`
- Los feriados nacionales de Ecuador 2025 y 2026

Verificar en la UI que el estado de sincronización muestra la BD lista.

## 3 — Cargar los horarios del personal

1. En la card azul **Horarios Personalizados**, hacer clic en **Importar**
2. Seleccionar el archivo `horarios_personal_ingreso.obd` (o `.ods` / `.csv`)
3. Verificar que muestra el número de horarios cargados correctamente

Los horarios quedan guardados en PostgreSQL y **no hay que volver a cargarlos** salvo que cambien. También se pueden agregar o editar personas individualmente con el botón **+ Agregar persona**.

## 4 — Primera sincronización

1. Seleccionar el rango de fechas del mes actual en la interfaz web
2. Hacer clic en **Sincronizar**
3. Esperar a que complete — la primera vez puede tardar varios minutos si el dispositivo tiene muchos registros históricos acumulados

---

---

# Activar autenticación en producción

Por defecto, si `APP_PASSWORD_HASH` está vacío en el `.env`, el sistema no pide contraseña. Esto es conveniente durante el desarrollo pero **no debe usarse en redes donde otros usuarios tengan acceso a la app**.

## Paso 1 — Generar el hash de la contraseña

Ejecutar **una sola vez** desde cualquier PC que tenga Python instalado:

```bash
# Linux / macOS
python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('TU_CONTRASEÑA_AQUI'))"
```

```powershell
# Windows PowerShell
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('TU_CONTRASEÑA_AQUI'))"
```

El comando imprime algo similar a:

```
scrypt:32768:8:1$abc123...$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Ese texto completo es el hash. **No es la contraseña en texto plano** — es seguro almacenarlo en el `.env`.

## Paso 2 — Añadir el hash al `.env`

Abrir el `.env` y pegar el hash en la variable correspondiente:

```ini
APP_PASSWORD_HASH=scrypt:32768:8:1$abc123...$xxxxxxxxxxxx...
```

No añadir comillas ni espacios alrededor del valor.

## Paso 3 — Aplicar el cambio

```bash
# Basta con reiniciar la app, no hace falta reconstruir ni reiniciar la BD
docker compose restart biometrico-app
```

Al acceder a `http://localhost:5000` (o `http://IP:5000`) el sistema mostrará la pantalla de login.

## Cambiar la contraseña en el futuro

Repetir el Paso 1 con la nueva contraseña, reemplazar el valor en `.env` y reiniciar:

```bash
docker compose restart biometrico-app
```

## Deshabilitar la autenticación temporalmente

Dejar `APP_PASSWORD_HASH` vacío y reiniciar:

```ini
APP_PASSWORD_HASH=
```

```bash
docker compose restart biometrico-app
```

---

---

# Actualizar el código (todos los escenarios)

Cuando hayas hecho cambios en el código y quieras aplicarlos.

## Si usas Git

**En tu máquina de desarrollo:**

```bash
git add .
git commit -m "descripción del cambio"
git push origin main
```

Asegúrate de que el `.gitignore` excluye estos archivos antes del primer push:

```
.env
__pycache__/
*.pyc
venv/
.venv/
data/
*.db
```

**En la máquina de producción (servidor o escritorio):**

Linux:
```bash
cd /ruta/al/proyecto
git pull origin main
docker compose up -d --build
```

Windows (PowerShell):
```powershell
cd C:\rrhh-biometrico
git pull origin main
docker compose up -d --build
```

Los datos de PostgreSQL (en el volumen `postgres_data`) **se conservan** — el volumen no se toca durante la reconstrucción.

## Si no usas Git

**Desde la máquina de desarrollo (Linux):**

```bash
tar -czf actualizacion.tar.gz \
  --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='venv' --exclude='.venv' --exclude='data/' --exclude='.env' \
  script_informe_asistencia/
```

Copiar el archivo al destino:

- A otro Linux por red: `scp actualizacion.tar.gz usuario@IP_SERVIDOR:/opt/`
- A Windows: copiar con cualquier explorador de archivos o pendrive

**En la máquina de producción:**

Linux:
```bash
cd /opt
tar -xzf actualizacion.tar.gz --strip-components=1 -C rrhh-biometrico
cd rrhh-biometrico
docker compose up -d --build
```

Windows (PowerShell) — descomprimir con el explorador de archivos o con:
```powershell
cd C:\rrhh-biometrico
tar -xzf C:\ruta\actualizacion.tar.gz --strip-components=1
docker compose up -d --build
```

## Si distribuyes por imagen (Escenario D)

Ver [sección D6](#d6--actualizar-la-aplicación-flujo-sin-código-fuente).

## Cuánto tarda la reconstrucción

| Cambió | Tiempo aproximado |
|--------|------------------|
| Solo archivos `.py`, `.html`, `.css` | menos de 30 segundos (Docker reutiliza capas cacheadas) |
| El archivo `requirements.txt` | 3–5 minutos (reinstala dependencias) |

Durante la reconstrucción el contenedor de la app se detiene brevemente. PostgreSQL sigue corriendo y los datos no se tocan.

---

---

# Comandos de mantenimiento frecuentes

## Gestión de servicios

```bash
# Ver si ambos contenedores están corriendo
docker compose ps

# Ver logs en tiempo real (ambos servicios)
docker compose logs -f

# Ver logs solo de la app
docker compose logs -f biometrico-app

# Ver logs solo de la base de datos
docker compose logs -f biometrico-db

# Reiniciar solo la app (aplica cambios del .env sin tocar la BD)
docker compose restart biometrico-app

# Reiniciar todo el stack
docker compose restart

# Detener el sistema (conserva los datos en los volúmenes)
docker compose down

# Ver todas las imágenes disponibles
docker images
```

## Backup y restauración de la base de datos

La base de datos ahora es PostgreSQL. Para hacer backup se usa `pg_dump`:

```bash
# Backup completo (SQL legible, comprimido)
docker exec biometrico-db pg_dump \
  -U asistencias_user \
  -d asistencias_db \
  --no-password \
  | gzip > backup_$(date +%Y%m%d_%H%M).sql.gz

# Backup en formato binario (más rápido para restaurar)
docker exec biometrico-db pg_dump \
  -U asistencias_user \
  -d asistencias_db \
  -Fc \
  > backup_$(date +%Y%m%d_%H%M).dump
```

**Restaurar desde backup SQL:**

```bash
# Detener la app pero dejar la BD corriendo
docker compose stop biometrico-app

# Restaurar (el flag -c limpia antes de restaurar)
gunzip -c backup_20260101_0030.sql.gz | \
  docker exec -i biometrico-db psql \
  -U asistencias_user \
  -d asistencias_db

# Volver a levantar la app
docker compose start biometrico-app
```

**Restaurar desde backup binario:**

```bash
docker compose stop biometrico-app

docker exec -i biometrico-db pg_restore \
  -U asistencias_user \
  -d asistencias_db \
  --clean \
  < backup_20260101_0030.dump

docker compose start biometrico-app
```

## Acceso directo a PostgreSQL

```bash
# Consola interactiva psql
docker exec -it biometrico-db psql -U asistencias_user -d asistencias_db

# Consultas rápidas sin entrar a la consola
docker exec biometrico-db psql -U asistencias_user -d asistencias_db \
  -c "SELECT COUNT(*) FROM istpet.asistencias;"

# Ver todas las tablas del tenant
docker exec biometrico-db psql -U asistencias_user -d asistencias_db \
  -c "\dt istpet.*"
```

## Migraciones de schema (Alembic)

Cuando se actualice el código y haya cambios en el schema de la BD:

```bash
# Ver la versión actual de la migración
docker compose exec biometrico-app alembic current

# Aplicar migraciones pendientes
docker compose exec biometrico-app alembic upgrade head

# Ver el historial de migraciones
docker compose exec biometrico-app alembic history
```

En la mayoría de actualizaciones de código **no es necesario correr Alembic manualmente** — `init_db()` al arrancar la app aplica los DDL faltantes con `IF NOT EXISTS`. Alembic es para migraciones destructivas o cambios de tipo de columna que no son automáticos.

---

---

# Referencia del `.env`

```ini
# ── Información del sistema ────────────────────────────────────────────
NOMBRE_SISTEMA=Informes Biométricos
NOMBRE_INSTITUCION=ISTPET

# ── Dispositivo biométrico ZK ──────────────────────────────────────────
# IP del dispositivo (ver en pantalla del equipo: Menú → Opciones → Comunicación)
ZK_IP=192.168.X.X

# Puerto del protocolo ZK (casi siempre 4370)
ZK_PORT=4370

# Contraseña del dispositivo — verificar en: Menú → Opciones → Comunicación → Contraseña del dispositivo
# Si nunca se configuró, el valor de fábrica es 0. Si se configuró, usar ese valor exacto.
ZK_PASSWORD=0

# Segundos de espera para conectar
ZK_TIMEOUT=120

# Protocolo UDP en lugar de TCP (más rápido en red local, probar si TCP es lento)
ZK_UDP=false

# Capacidad máxima del dispositivo (para estimar % de uso)
ZK_CAPACIDAD_MAX=80000

# ── Sincronización automática ──────────────────────────────────────────
# true = activa sync en background; false = solo manual desde la interfaz
SYNC_AUTO=false

# Hora del sync nocturno completo (HH:MM)
SYNC_HORA_NOCTURNA=00:30

# Cada cuántos minutos hacer un sync parcial durante la jornada
SYNC_INTERVALO_MIN=480

# ── Rutas de datos (internas del contenedor — NO cambiar) ──────────────
DATA_DIR=/data
UPLOAD_FOLDER=/data/uploads
REPORTS_FOLDER=/data/reports

# ── PostgreSQL ─────────────────────────────────────────────────────────
# Usuario y contraseña de la base de datos — elegir una contraseña segura
POSTGRES_USER=asistencias_user
POSTGRES_PASSWORD=cambiar_esto_en_produccion
POSTGRES_DB=asistencias_db

# URL de conexión — en desarrollo local usar localhost; en Docker lo sobreescribe el compose
DATABASE_URL=postgresql://asistencias_user:cambiar_esto_en_produccion@localhost:5432/asistencias_db

# Slug del tenant activo (nombre del schema en PostgreSQL)
TENANT_DEFAULT=istpet

# Clave para cifrar contraseñas de dispositivos adicionales en la BD
# Generar con: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DB_ENCRYPTION_KEY=generar_con_comando_de_arriba

# ── Flask ──────────────────────────────────────────────────────────────
# Clave secreta para sesiones Flask — generar con:
#   python3 -c "import secrets; print(secrets.token_hex(32))"
FLASK_SECRET_KEY=cambiar_esto_por_una_clave_larga_y_segura

FLASK_HOST=0.0.0.0
FLASK_PORT=5000

# Nunca activar debug en producción
FLASK_DEBUG=false

# ── Autenticación de acceso ────────────────────────────────────────────
# Dejar vacío para deshabilitar la autenticación (modo desarrollo/interno)
# Para generar el hash de tu contraseña:
#   python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('tu_clave'))"
APP_PASSWORD_HASH=

# Contraseña separada para operaciones sensibles (limpiar el dispositivo ZK)
APP_MAINTENANCE_PASSWORD_HASH=

# ── Correo electrónico (SMTP) ──────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=notificaciones@tuinstituto.edu.ec
SMTP_PASSWORD=tu_contraseña_o_app_password
SMTP_FROM=notificaciones@tuinstituto.edu.ec
SMTP_USE_TLS=true
```

---

---

# Solución de problemas

### Un contenedor aparece en estado "Exit" o "Restarting"

```bash
# Ver qué servicio falló y por qué
docker compose ps
docker compose logs biometrico-app
docker compose logs biometrico-db
```

Causas frecuentes para `biometrico-db`:
- `POSTGRES_PASSWORD` no está configurado en el `.env`.
- El volumen `postgres_data` está corrupto (muy raro). Verificar con `docker volume inspect`.

Causas frecuentes para `biometrico-app`:
- La app arrancó antes de que PostgreSQL estuviera listo. El healthcheck debería evitarlo, pero si falló, reiniciar con `docker compose restart biometrico-app`.
- `DATABASE_URL` no apunta al host `db` dentro del compose. Verificar que el `docker-compose.yml` sobreescribe la variable con `@db:5432`.
- El archivo `.env` tiene valores mal formateados (espacios alrededor del `=`, comillas innecesarias).

---

### "Port 5000 already in use"

Cambiar el puerto en `docker-compose.yml`:

```yaml
ports:
  - "5001:5000"
```

Luego `docker compose up -d --build`. Acceder en `http://localhost:5001`.

---

### "Port 5432 already in use"

Hay otra instancia de PostgreSQL corriendo en el host. Opciones:

**A) Cambiar el puerto de mapeo** (el Puerto interno del contenedor sigue siendo 5432):

En `docker-compose.yml`, servicio `db`:
```yaml
ports:
  - "127.0.0.1:5433:5432"   # mapear al 5433 en el host
```

La app dentro de Docker siempre usa el puerto interno 5432 — no es necesario cambiar `DATABASE_URL`.

**B) No exponer el puerto** (si solo la app interna necesita la BD):

```yaml
# Comentar o eliminar el bloque ports del servicio db
# ports:
#   - "127.0.0.1:5432:5432"
```

La app sigue conectando porque ambos contenedores comparten la red interna de Docker.

---

### No se puede acceder desde otra PC en la red

- **Linux:** verificar el firewall: `sudo ufw allow 5000/tcp`
- **Windows:** el firewall de Windows puede bloquear el puerto. Ir a: Panel de Control → Firewall de Windows Defender → Reglas de entrada → Nueva regla → Puerto 5000 TCP → Permitir.

---

### El dispositivo ZK aparece como "no accesible"

Seguir este orden de verificación:

**1 — Verificar IP y conectividad de red desde la máquina host** (no desde el contenedor):

Linux:
```bash
ping IP_DEL_ZK
```
Windows CMD:
```cmd
ping IP_DEL_ZK
```

Si el ping no responde: el problema es de red. Verificar cable, switch y que la IP en `.env` (`ZK_IP`) coincide con la que muestra el dispositivo en `Menú → Opciones → Comunicación`.

**2 — Verificar que el puerto 4370 está accesible:**

```bash
# Linux
nc -zv -w 3 IP_DEL_ZK 4370

# Windows PowerShell
Test-NetConnection -ComputerName IP_DEL_ZK -Port 4370
```

Si el ping responde pero el puerto no, el dispositivo puede estar reiniciando su servicio o tiene un firewall. Reiniciar el equipo ZK.

**3 — Verificar la contraseña del dispositivo:**

Si el puerto está abierto pero la app sigue sin conectar, el error interno suele ser `Unauthenticated`. Esto significa que `ZK_PASSWORD` en `.env` no coincide con la contraseña configurada en el dispositivo.

- En el dispositivo: `Menú → Opciones → Comunicación → Contraseña del dispositivo`
- Corregir el valor en `.env` y reiniciar:
  ```bash
  docker compose restart biometrico-app
  ```

**4 — Si todo lo anterior está bien, probar con UDP:**

```ini
ZK_UDP=true
```
```bash
docker compose restart biometrico-app
```

**5 — El ZK admite una sola conexión simultánea.** Si el software del fabricante u otra instancia está conectada, cerrarla antes de sincronizar.

---

### El sistema redirige siempre al login

Si configuraste `APP_PASSWORD_HASH` en el `.env` y el sistema no deja entrar:

- Verificar que el hash fue generado correctamente con `werkzeug.security.generate_password_hash` y no copiado con espacios extra.
- Verificar que `FLASK_SECRET_KEY` tiene un valor fijo y no cambia entre reinicios (si cambia, las sesiones existentes se invalidan).
- Para deshabilitar temporalmente la autenticación: dejar `APP_PASSWORD_HASH=` vacío y reiniciar con `docker compose restart biometrico-app`.

---

### `alembic upgrade head` falla con "already exists"

La migración `0001` usa `CREATE TABLE IF NOT EXISTS` — es idempotente. Si falla con otro error, verificar:

```bash
# Ver el estado actual de Alembic dentro del contenedor
docker compose exec biometrico-app alembic current

# Si no está en head, aplicar manualmente
docker compose exec biometrico-app alembic upgrade head
```

Si la tabla `alembic_version` no existe aún en el schema del tenant, Alembic la creará automáticamente.

---

### Docker Desktop no arranca en Windows

- Verificar que la virtualización está habilitada en la BIOS del PC.
- En Windows 11: asegurarse de que WSL 2 está instalado: abrir PowerShell como administrador y ejecutar `wsl --install`.
- Reiniciar Docker Desktop desde el menú de la bandeja del sistema.

---

### `git pull` falla por conflictos con archivos locales

```bash
git status

# Si .env o data/ se rastrean por error, excluirlos del repo:
echo ".env" >> .gitignore
echo "data/" >> .gitignore
git rm --cached .env
git rm -r --cached data/
git commit -m "excluir archivos locales del repo"
git pull origin main
```

---

### `docker load` falla con "no such file"

Verificar que el archivo `.tar` y el `docker-compose.yml` están en la misma carpeta desde la que se ejecuta el comando. En Windows, usar la ruta completa si es necesario:

```powershell
docker load -i C:\rrhh\rrhh-app.tar
docker load -i C:\rrhh\rrhh-postgres.tar
```

---

*Sistema de Informes Biométricos — RRHH ISTPET*
