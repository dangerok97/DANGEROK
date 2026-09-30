FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir ".[postgres]"
# Utente non privilegiato
RUN useradd -m -u 10001 dgk && chown -R dgk /srv
USER dgk
EXPOSE 8000
# $PORT e' impostata da molti provider; in locale vale 8000. --proxy-headers: l'HTTPS e' terminato dal provider.
CMD ["sh", "-c", "uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
