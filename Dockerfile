# Use an official Python runtime as a parent image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# Install system dependencies (FFmpeg is critical for this project)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Create necessary directories for processing
RUN mkdir -p uploads outputs temp

# The application runs on port 10000
EXPOSE 10000

# Run gunicorn to serve the Flask app
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "600", "project1:app"]
