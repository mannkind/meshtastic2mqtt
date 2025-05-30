FROM python:3.9-slim
WORKDIR /app
RUN apt update && \
    apt install -y bluez && \
    pip install --no-cache-dir meshtastic paho-mqtt cryptography && \
    rm -rf /var/lib/apt/lists/*
COPY src/lib /app/lib
COPY src/meshtastic2mqtt.py /app/
CMD ["python", "meshtastic2mqtt.py"]