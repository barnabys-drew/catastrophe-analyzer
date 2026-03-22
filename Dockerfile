FROM python:3.12-slim

LABEL org.opencontainers.image.title="catastrophe-analyzer"

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Work in src so the project's relative config/data defaults keep working
WORKDIR /app/src

# Run monitor in foreground (Docker keeps container alive).
# Use ENTRYPOINT so `docker run image --once --quiet` passes args to monitor.py.
ENTRYPOINT ["python", "-u", "monitor.py"]
CMD []

