FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN python -m pip install --no-cache-dir ".[web]"

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120 web.app:app"]
