FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY python/requirements.txt python/requirements-ia.txt ./
RUN pip install --no-cache-dir -r requirements-ia.txt

COPY python/app ./app
COPY python/migrate.py python/create_admin.py python/configure_dev.py python/seed_demo.py ./
COPY sql /sql

RUN mkdir -p /app/uploads/fotos /app/uploads/logos /app/uploads/curriculos

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
