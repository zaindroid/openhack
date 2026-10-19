FROM python:3.11-slim
WORKDIR /srv
COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt
COPY whycore /srv/whycore
COPY app /srv/app
RUN if [ -f /srv/app/requirements.txt ]; then pip install --no-cache-dir -r /srv/app/requirements.txt; fi
ENV PYTHONPATH=/srv PORT=8080 DATA_BACKEND=duckdb MEMORY_DIR=/srv/data/memory
EXPOSE 8080
HEALTHCHECK --interval=30s --retries=5 CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/healthz')"
CMD ["sh", "-c", "uvicorn whycore.app:app --host 0.0.0.0 --port ${PORT}"]
