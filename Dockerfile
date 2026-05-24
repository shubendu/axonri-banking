FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential curl git ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel

# Install axonri-core (no torch, no docling)
COPY axonri-core/ /axonri-core/
RUN pip install --no-cache-dir /axonri-core/

# Install banking app dependencies
COPY axonri-banking/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY axonri-banking/ /app/

RUN mkdir -p /data/corpus/rbi/ucb /data/corpus/rbi/crosscutting \
             /data/vectors /data/logs /data/models

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]