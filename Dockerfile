# Imagen base ligera de Python sobre Debian: necesaria porque el navegador
# Firefox de Playwright requiere bibliotecas del sistema operativo (las
# instala el propio comando `playwright install --with-deps`).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt \
    && playwright install --with-deps firefox

COPY . .

EXPOSE 8000

# Railway y Render inyectan el puerto a usar en la variable $PORT;
# localmente (docker run sin -e PORT) cae a 8000.
CMD ["sh", "-c", "uvicorn api_nit_bolivia:app --host 0.0.0.0 --port ${PORT:-8000}"]
