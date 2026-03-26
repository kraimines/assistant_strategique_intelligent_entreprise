
# ===========================================================================
# Dockerfile — Backend FastAPI Talan
# ===========================================================================
FROM python:3.11-slim

# Évite les .pyc et les buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DEFAULT_TIMEOUT=600

WORKDIR /app

# Dépendances système : curl (healthcheck) + libpq (psycopg2-binary)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python en premier
# (layer Docker mis en cache si requirements.txt ne change pas)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --default-timeout=600 -r requirements.txt

# Copier le code source
COPY . .

# Port exposé
EXPOSE 8000

# Démarrage avec hot-reload en développement
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]