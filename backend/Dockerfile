FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY geopol ./geopol
RUN pip install -c requirements.lock . \
    && groupadd --gid 10001 geopol \
    && useradd --uid 10001 --gid geopol --no-create-home geopol \
    && mkdir -p /app/data/storage \
    && chown -R geopol:geopol /app/data

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "geopol.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
