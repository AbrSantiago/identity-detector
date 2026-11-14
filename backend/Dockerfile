# Imagen del backend (FastAPI). Base oficial de astral con uv + Python 3.12.
# El contexto de build es la RAÍZ del repo (ver docker-compose.yml), porque el
# backend también sirve tracker/fp.js, que vive fuera de backend/.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app/backend

# Dependencias primero (capa cacheable): solo los archivos de lock.
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev

# Código de la app y el tracker (servido por el backend en /tracker/fp.js).
COPY backend/app ./app
COPY tracker /app/tracker

ENV PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 8000

# Un solo worker: el estado vive en memoria (dict de identidades, historial).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
