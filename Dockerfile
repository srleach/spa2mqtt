FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY spa2mqtt ./spa2mqtt
COPY definitions ./definitions
RUN pip install --no-cache-dir .

# config.yml is read from the working directory; mount it at /app/config.yml.
CMD ["spa2mqtt", "run", "-c", "/app/config.yml"]
