FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements-utf16.txt
RUN python - <<'PY'
from pathlib import Path
raw = Path('/tmp/requirements-utf16.txt').read_bytes()
try:
    text = raw.decode('utf-16')
except UnicodeError:
    text = raw.decode('utf-8')
Path('/tmp/requirements.txt').write_text(text, encoding='utf-8')
PY
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY app.py /app/app.py
COPY model /model
ENV PORT=5001
CMD ["python", "app.py"]
