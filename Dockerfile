FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema:
# - libpq-dev: requerido por psycopg2-binary en runtime
# - postgresql-client-16: provee `pg_dump` para backups portables (Fase 2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python primero (aprovecha cache de capas Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY . .

# Crear directorio de datos (se sobreescribe por el volume en runtime)
RUN mkdir -p /data/uploads /data/reports /data/backups

ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# gunicorn con 1 worker y 4 threads:
# - 1 worker mantiene el estado en memoria (job tracking, scheduler)
# - 4 threads permiten atender múltiples peticiones concurrentes
# - timeout 120s para operaciones largas de sync y generación de PDF
# - wsgi:app es el entrypoint canónico post-refactor (ADR-0001)
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "wsgi:app"]
