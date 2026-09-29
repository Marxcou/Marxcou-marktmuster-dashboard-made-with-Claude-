FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic.ini ./
COPY alembic ./alembic
COPY entrypoint.sh ./
# CRLF-fest: entfernt Windows-Zeilenenden, falls der Checkout welche enthält
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh
CMD ["./entrypoint.sh", "api"]
