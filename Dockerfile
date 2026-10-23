FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl — healthcheck; pango + DejaVu — WeasyPrint (chek, hisobot PDF, o'zbek harflari bilan)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
       libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
RUN pip install -r requirements/prod.txt

COPY . .

# Statik fayllar (admin, swagger) whitenoise orqali. Build paytida MB kerak emas.
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=build-only \
    DATABASE_URL=postgres://x:x@localhost:5432/x \
    python manage.py collectstatic --noinput

RUN chmod +x docker/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
