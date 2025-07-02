# Dockerfile
FROM python:3.10

# Install system-level dependencies
RUN apt-get update && apt-get install -y portaudio19-dev

# Set working directory
WORKDIR /app

# Copy project files
COPY . /app

# Install Python packages
RUN pip install --upgrade pip && pip install -r requirements.txt

# Run Streamlit app
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.enableCORS=false"]

# Install system dependencies including ffmpeg
RUN apt-get update && apt-get install -y portaudio19-dev ffmpeg

