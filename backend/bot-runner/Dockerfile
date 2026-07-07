FROM python:3.11-slim

# Install system dependencies: Chromium, Xvfb, PulseAudio, ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-driver \
    xvfb pulseaudio pulseaudio-utils \
    ffmpeg \
    libpulse0 libpulse-dev \
    libopus-dev \
    curl wget ca-certificates \
    fonts-liberation fonts-noto \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DISPLAY=:99
ENV PULSE_SERVER=unix:/tmp/pulse.sock
ENV PYTHONUNBUFFERED=1

EXPOSE 5001

CMD ["python", "main.py"]
