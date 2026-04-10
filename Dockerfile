FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e .
ENV DS_CONTROL_DB_URL=postgresql+psycopg://datashield:datashield@postgres:5432/datashield
ENV DS_BOOTSTRAP_ADMIN=admin
ENV DS_BOOTSTRAP_PASSWORD=admin12345
ENV DATASHIELD_AUDIT_KEY=change-me-in-production
EXPOSE 8080
CMD ["uvicorn", "datashield.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
