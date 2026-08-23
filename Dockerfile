# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Install system dependencies (FFmpeg is critical for this project)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copy the rest of the application code into the container
COPY . .

# Create necessary directories for processing
RUN mkdir -p uploads outputs temp

# The application runs on port 5000 (standard for Flask)
EXPOSE 5000

# Run gunicorn to serve the Flask app
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "600", "app:app"]
