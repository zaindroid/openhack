# Public read-only view of Mosca (app/public/server.py). Build context: the repo root.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30" "httpx>=0.27"
WORKDIR /srv
COPY app/public/server.py /srv/server.py
COPY whycore/static/live.html /srv/live.html
ENV PORT=8080 UPSTREAM=http://lab-mosca:8080 LIVE_HTML=/srv/live.html
EXPOSE 8080
USER nobody
HEALTHCHECK --interval=30s --retries=5 CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/healthz')"
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
