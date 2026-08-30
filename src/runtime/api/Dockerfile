FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN groupadd --gid 11001 jcareer-api \
    && useradd --uid 11001 --gid 11001 --no-create-home --shell /usr/sbin/nologin jcareer-api
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=11001:11001 app ./app

EXPOSE 8000
USER 11001:11001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
