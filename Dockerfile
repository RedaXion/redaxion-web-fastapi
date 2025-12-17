# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Install system dependencies
# LibreOffice is required for docx -> pdf conversion
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including LibreOffice for PDF conversion
RUN apt-get update && apt-get install -y \
    libreoffice \
    libreoffice-writer \
    fonts-liberation \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Instalar reportlab explícitamente (fallback si LibreOffice falla)
RUN pip install --no-cache-dir reportlab pillow

# Copy application code
COPY . .

# Create directories for generated files
RUN mkdir -p static/generated

# Expose port
EXPOSE 8000

# Run with uvicorn with increased limits for large file uploads
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-max-request-line", "0", "--limit-concurrency", "100"]
