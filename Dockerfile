FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose both ports
EXPOSE 8001 8080

# Default: start the FastAPI client server
CMD ["uvicorn", "client.main:app", "--host", "0.0.0.0", "--port", "8080"]