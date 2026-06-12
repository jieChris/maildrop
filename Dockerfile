FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml /app/
COPY src /app/src

RUN pip install --no-cache-dir .

COPY alembic.ini /app/
COPY migrations /app/migrations

EXPOSE 8000

CMD ["uvicorn", "maildrop.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
