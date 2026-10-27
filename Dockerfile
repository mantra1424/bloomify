# Production image: Python + gunicorn, runs as a non-root user.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=bloomproject.settings.prod \
    PORT=8000

WORKDIR /app

RUN useradd --create-home --uid 1000 bloomify

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=bloomify:bloomify . .

# Collect static files at build time (dummy values: nothing connects to a database here).
RUN DJANGO_SECRET_KEY=build-only DATABASE_URL=sqlite:////tmp/build.db \
    python manage.py collectstatic --noinput \
 && mkdir -p media && chown -R bloomify:bloomify staticfiles media

USER bloomify
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz/', timeout=4)"

CMD ["sh", "-c", "gunicorn bloomproject.wsgi:application --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-3} --access-logfile - --error-logfile -"]
