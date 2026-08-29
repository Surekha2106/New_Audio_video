# Use an official Python runtime as a parent image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# Install FFmpeg, wget, unzip, ca-certificates and required system packages
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    wget \
    unzip \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Download and setup Vosk English speech recognition model
RUN wget -q https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip && \
    unzip -q vosk-model-small-en-us-0.15.zip && \
    mv vosk-model-small-en-us-0.15 VoskModel && \
    rm vosk-model-small-en-us-0.15.zip

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
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--threads", "8", "--timeout", "600", "project1:app"]
