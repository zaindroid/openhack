FROM node:22-slim AS node
FROM python:3.11-slim
COPY --from=node /usr/local/bin/node /usr/local/bin/node
WORKDIR /srv
COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt
COPY whycore /srv/whycore
COPY app /srv/app
RUN if [ -f /srv/app/requirements.txt ]; then pip install --no-cache-dir -r /srv/app/requirements.txt; fi
ENV PYTHONPATH=/srv PORT=8080 DATA_BACKEND=duckdb MEMORY_DIR=/srv/data/memory METERLESS_ENGINES=on METERLESS_ENGINES_URL=http://127.0.0.1:8790
EXPOSE 8080
HEALTHCHECK --interval=30s --retries=5 CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/healthz')"
# Meterless engines sidecar (H-MEM, World Model, Markovian) on 127.0.0.1:8790, then the app. METERLESS_ENGINES=off skips it.
CMD ["sh", "-c", "if [ \"$METERLESS_ENGINES\" = on ]; then METERLESS_DIR=$MEMORY_DIR/meterless node --experimental-transform-types --no-warnings whycore/meterless/server.ts & fi; exec uvicorn whycore.app:app --host 0.0.0.0 --port ${PORT}"]
