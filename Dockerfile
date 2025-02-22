FROM python:3.9-slim
WORKDIR /app
RUN apt update && \
    apt install -y bluez && \
    pip install --no-cache-dir meshtastic paho-mqtt && \
    rm -rf /var/lib/apt/lists/*
COPY meshtastic2mqtt.py /app
CMD ["python", "meshtastic2mqtt.py"]