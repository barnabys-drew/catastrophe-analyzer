FROM python:3.14-slim

LABEL org.opencontainers.image.title="catastrophe-analyzer"

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Work in src so the project's relative config/data defaults keep working
WORKDIR /app/src

# Run monitor in foreground (Docker keeps container alive).
# Use ENTRYPOINT so `docker run image --once --quiet` passes args to monitor.py.
ENV CATASTROPHE_HEALTH_MAX_AGE_SECONDS=2400
HEALTHCHECK --interval=60s --timeout=10s --start-period=180s --retries=3 \
  CMD ["python", "-u", "healthcheck.py"]

ENTRYPOINT ["python", "-u", "monitor.py"]
CMD []

