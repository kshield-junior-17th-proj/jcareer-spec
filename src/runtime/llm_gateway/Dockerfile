FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN groupadd --gid 11002 jcareer-llm \
    && useradd --uid 11002 --gid 11002 --no-create-home --shell /usr/sbin/nologin jcareer-llm \
    && install -d -o 11002 -g 11002 -m 0750 /data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=11002:11002 app ./app

EXPOSE 8200
USER 11002:11002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
