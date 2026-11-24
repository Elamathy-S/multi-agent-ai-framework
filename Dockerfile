FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/finance_sim.db

RUN useradd --create-home app && mkdir /data && chown app /data
USER app

EXPOSE 8001 8080

# Default: the API server. docker-compose overrides this for the MCP server.
CMD ["uvicorn", "client.main:app", "--host", "0.0.0.0", "--port", "8080"]
