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
> docker compose up -d --build   # primera vez
> docker compose up -d --build   # para aplicar actualizaciones
> docker compose logs -f          # ver qué hace
> ```

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

---

## A4 — Iniciar el sistema

```bash
docker compose up -d --build
```

La primera vez descarga la imagen base de Python e instala las dependencias: puede tardar 3–5 minutos.

Verificar que está corriendo:

```bash
docker compose ps
```

La columna `Status` debe decir `Up`. Abrir el navegador en:

```
http://localhost:5000
```

---

## A5 — Comportamiento al reiniciar la PC

El contenedor tiene `restart: unless-stopped`. Esto significa:

- Si reinicias la PC: el contenedor **arranca automáticamente** cuando Docker arranca.
- Docker arranca automáticamente con el sistema en la mayoría de distribuciones Linux tras la instalación.
- Si detuviste el contenedor manualmente con `docker compose down`, **no** arrancará solo al reiniciar.

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

Verificar:

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

Si el servidor tiene UFW activado:

```bash
sudo ufw allow 5000/tcp
sudo ufw status
```

---

## B6 — Optimización de red para Linux (opcional)

En Linux con Docker Engine, existe una alternativa más directa para el networking que elimina la capa NAT. Editar `docker-compose.yml` y cambiar:

```yaml
# Comentar el bloque ports:
# ports:
#   - "5000:5000"

# Descomentar esta línea:
network_mode: host
```

Reiniciar:

```bash
docker compose up -d --build
```

Con `network_mode: host` el contenedor usa directamente la red del host. Útil si el dispositivo ZK está en una subred específica que no es alcanzable por el NAT de Docker. **No usar esta opción en Windows ni macOS.**

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

Abrir el navegador en:

```
http://localhost:5000
```

---

## C5 — Comportamiento al reiniciar Windows

Docker Desktop tiene una opción para arrancar con Windows. Para activarla:

1. Hacer clic derecho en el ícono de Docker en la barra de tareas → **Settings**
2. En la sección **General** → activar **"Start Docker Desktop when you sign in to your computer"**

El contenedor tiene `restart: unless-stopped`, así que cuando Docker Desktop arranque, el contenedor también lo hará automáticamente.

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

Usa este flujo cuando quieres instalar el sistema en otra PC **sin copiar el código fuente** — solo la imagen Docker compilada. Es el método más rápido para entregar la aplicación a máquinas de producción que no tienen acceso al repositorio.

---

## D1 — Construir y exportar la imagen (desde la PC de desarrollo)

Primero asegurarse de que la imagen está construida:

```bash
docker compose build
```

Luego exportarla a un archivo `.tar`:

```bash
docker save -o ~/Desktop/rrhh-biometrico.tar script_informe_asistencia-rrhh-app
```

> El nombre de la imagen (`script_informe_asistencia-rrhh-app`) se puede confirmar con `docker images`.

---

## D2 — Archivos a transferir

Copiar los siguientes tres archivos a la PC de destino (USB, Google Drive, etc.):

| Archivo | Descripción |
|---|---|
| `rrhh-biometrico.tar` | Imagen Docker exportada (contiene toda la aplicación) |
| `docker-compose.yml` | Configuración del contenedor |
| `.env` | Variables de entorno (IP del ZK, contraseña, etc.) |

Colocarlos todos en la misma carpeta, por ejemplo `C:\rrhh\` en Windows o `/opt/rrhh/` en Linux.

> **Atención con el `.env`:** contiene la contraseña del dispositivo y `FLASK_SECRET_KEY`. Transferirlo por un medio seguro y no subirlo a repositorios públicos.

---

## D3 — Preparar el `docker-compose.yml` en la PC de destino

En la PC de destino, abrir el `docker-compose.yml` y reemplazar la línea:

```yaml
build: .
```

por:

```yaml
image: script_informe_asistencia-rrhh-app
```

Esto es necesario porque en la PC de destino no existe el código fuente — solo se usará la imagen ya compilada.

---

## D4 — Cargar la imagen e iniciar (Linux)

```bash
docker load -i rrhh-biometrico.tar
docker compose up -d
```

Verificar:

```bash
docker compose ps
```

Acceder en: `http://localhost:5000`

---

## D5 — Cargar la imagen e iniciar (Windows)

Abrir PowerShell en la carpeta donde están los archivos:

```powershell
docker load -i rrhh-biometrico.tar
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

# 2. Exportar la nueva imagen
docker save -o ~/Desktop/rrhh-biometrico-v2.tar script_informe_asistencia-rrhh-app
```

En la PC de destino:

```bash
# Detener el contenedor actual
docker compose down

# Cargar la nueva imagen (reemplaza la anterior)
docker load -i rrhh-biometrico-v2.tar

# Volver a levantar
docker compose up -d
```

> La base de datos con los registros de asistencia **no se pierde** — el volumen `db_data` se mantiene entre actualizaciones.

---

---

# Primer uso (todos los escenarios)

Una vez que el sistema esté corriendo, estos pasos son iguales sin importar el sistema operativo.

## 1 — Acceder a la aplicación

- **Escritorio o Windows:** abrir el navegador en `http://localhost:5000`
- **Servidor:** abrir `http://IP_DEL_SERVIDOR:5000` desde cualquier PC en la red

Si `APP_PASSWORD_HASH` está configurado en el `.env`, el sistema pedirá contraseña. Si está vacío, no hay autenticación (modo desarrollo).

## 2 — Cargar los horarios del personal

1. En la card azul **Horarios Personalizados**, hacer clic en **Importar**
2. Seleccionar el archivo `horarios_personal_ingreso.obd` (o `.ods` / `.csv`)
3. Verificar que muestra el número de horarios cargados correctamente

Los horarios quedan guardados en la base de datos y **no hay que volver a cargarlos** salvo que cambien. También se pueden agregar o editar personas individualmente con el botón **+ Agregar persona**.

## 3 — Primera sincronización

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
# Basta con reiniciar, no hace falta reconstruir la imagen
docker compose restart
```

Al acceder a `http://localhost:5000` (o `http://IP:5000`) el sistema mostrará la pantalla de login.

## Cambiar la contraseña en el futuro

Repetir el Paso 1 con la nueva contraseña, reemplazar el valor en `.env` y reiniciar:

```bash
docker compose restart
```

No hace falta reconstruir la imagen (`--build`) para este cambio.

## Deshabilitar la autenticación temporalmente

Dejar `APP_PASSWORD_HASH` vacío y reiniciar:

```ini
APP_PASSWORD_HASH=
```

```bash
docker compose restart
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

La base de datos, los horarios cargados y los registros sincronizados **se conservan** — el volumen `db_data` no se toca durante la reconstrucción.

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

Durante la reconstrucción el contenedor anterior se detiene brevemente.

---

---

# Comandos de mantenimiento frecuentes

Estos comandos son los mismos en Linux y Windows (PowerShell):

```bash
# Ver si el contenedor está corriendo
docker compose ps

# Ver logs en tiempo real
docker compose logs -f

# Reiniciar sin reconstruir (aplica cambios del .env)
docker compose restart

# Detener el sistema (conserva los datos)
docker compose down

# Ver todas las imágenes disponibles
docker images

# Hacer backup de la base de datos
docker cp rrhh-biometrico:/data/asistencias.db ./backup_$(date +%Y%m%d).db

# En Windows PowerShell el backup es:
# docker cp rrhh-biometrico:/data/asistencias.db .\backup.db

# Restaurar un backup
docker compose down
docker compose up -d
docker cp ./backup_20260101.db rrhh-biometrico:/data/asistencias.db
docker compose restart
```

---

---

# Referencia del `.env`

```ini
# ── Dispositivo biométrico ZK ──────────────────────────────────────────
# IP del dispositivo (ver en pantalla del equipo: Menú → Opciones → Comunicación)
ZK_IP=192.168.X.X

# Puerto del protocolo ZK (casi siempre 4370)
ZK_PORT=4370

# Contraseña del dispositivo — verificar en: Menú → Opciones → Comunicación → Contraseña del dispositivo
# Si nunca se configuró, el valor de fábrica es 0. Si se configuró, usar ese valor exacto.
ZK_PASSWORD=0

# Segundos de espera para conectar
ZK_TIMEOUT=5

# Protocolo UDP en lugar de TCP (más rápido en red local, probar si TCP es lento)
ZK_UDP=false

# ── Sincronización automática ──────────────────────────────────────────
# true = activa sync en background; false = solo manual desde la interfaz
SYNC_AUTO=false

# Hora del sync nocturno completo (HH:MM)
SYNC_HORA_NOCTURNA=00:30

# Cada cuántos minutos hacer un sync parcial durante la jornada
SYNC_INTERVALO_MIN=30

# ── Rutas de datos (internas del contenedor — NO cambiar) ──────────────
DB_PATH=/data/asistencias.db
UPLOAD_FOLDER=/data/uploads
REPORTS_FOLDER=/data/reports

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
# Luego pegar el resultado aquí:
APP_PASSWORD_HASH=
```

---

---

# Solución de problemas

### El contenedor aparece en estado "Exit"

```bash
docker compose logs rrhh-app
```

Causas frecuentes:
- El archivo `.env` no existe o tiene valores mal formateados (espacios alrededor del `=`, comillas innecesarias).
- El puerto 5000 ya está en uso. En Linux: `sudo ss -tlnp | grep 5000`. En Windows: `netstat -ano | findstr :5000`.

---

### "Port 5000 already in use"

Cambiar el puerto en `.env`:

```ini
FLASK_PORT=5001
```

Y en `docker-compose.yml` cambiar `"5000:5000"` por `"5001:5001"`. Luego `docker compose up -d --build`.

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
  docker compose restart
  ```

**4 — Si todo lo anterior está bien, probar con UDP:**

```ini
ZK_UDP=true
```
```bash
docker compose restart
```

**5 — El ZK admite una sola conexión simultánea.** Si el software del fabricante u otra instancia está conectada, cerrarla antes de sincronizar.

---

### El sistema redirige siempre al login

Si configuraste `APP_PASSWORD_HASH` en el `.env` y el sistema no deja entrar:

- Verificar que el hash fue generado correctamente con `werkzeug.security.generate_password_hash` y no copiado con espacios extra.
- Verificar que `FLASK_SECRET_KEY` tiene un valor fijo y no cambia entre reinicios (si cambia, las sesiones existentes se invalidan).
- Para deshabilitar temporalmente la autenticación: dejar `APP_PASSWORD_HASH=` vacío y reiniciar con `docker compose restart`.

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
docker load -i C:\rrhh\rrhh-biometrico.tar
```

---

*Sistema de Informes Biométricos — RRHH ISTPET*
