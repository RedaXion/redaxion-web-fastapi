# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Install system dependencies
# LibreOffice is required for docx -> pdf conversion
RUN apt-get update && apt-get install -y \
    libreoffice \
    default-jre \
    libreoffice-java-common \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Run app.py when the container launches
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
