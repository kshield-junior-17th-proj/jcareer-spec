FROM python:3.12-slim

ARG RUNTIME_UID=11001
ARG RUNTIME_GID=11001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid "${RUNTIME_GID}" jcareer-broker \
    && useradd --uid "${RUNTIME_UID}" --gid "${RUNTIME_GID}" \
        --no-create-home --shell /usr/sbin/nologin jcareer-broker

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

USER ${RUNTIME_UID}:${RUNTIME_GID}
CMD ["python", "-m", "app.main"]
