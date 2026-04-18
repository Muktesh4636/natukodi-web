# Django Backend Dockerfile
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AUTOBAHN_USE_NVX=0

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    tesseract-ocr \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create directories for media and static files
RUN mkdir -p /app/media /app/staticfiles /app/logs

# Collect static files (will be done at runtime if needed)
# RUN python manage.py collectstatic --noinput

# Expose port
EXPOSE 8080

# Default command (can be overridden in docker-compose)
CMD ["gunicorn", "dice_game.asgi:application", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8080", "--workers", "2"]

