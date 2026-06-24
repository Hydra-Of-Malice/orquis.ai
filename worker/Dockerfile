FROM python:3.11-slim

# System deps: ffmpeg + SpeechBrain audio libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 libsox-dev sox curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info", "-Q", "transcription,analysis", "-c", "4"]
