import logging
import sys
import os
from lib.meshtastic import setupMeshtastic
from lib.mqtt import setupMQTT

def main() -> None:
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Setup environment variables
    mqttHost = os.environ.get("MESHTASTIC2MQTT_MQTT_HOST", "mqtt.davekeogh.com")
    mqttPort = int(os.environ.get("MESHTASTIC2MQTT_MQTT_PORT", "1883"))
    mqttUsername = os.environ.get("MESHTASTIC2MQTT_MQTT_USERNAME", "meshdev")
    mqttPassword = os.environ.get("MESHTASTIC2MQTT_MQTT_PASSWORD", "large4cats")
    mqttTopicBase = os.environ.get("MESHTASTIC2MQTT_MQTT_TOPIC_BASE", "msh/US/2/e")
    bleInterval = int(os.environ.get("MESHTASTIC2MQTT_MESHTASTIC_INTERVAL", "67"))
    bleAddress = os.environ.get(
        "MESHTASTIC2MQTT_MESHTASTIC_ADDRESS", "CF:B0:EF:3C:15:0A"
    )

    # Setup MQTT
    logging.info("Starting setup of MQTT")
    mqttClient = setupMQTT(
        mqttHost, mqttPort, mqttUsername, mqttPassword, mqttTopicBase
    )
    logging.info("Finished setup of MQTT")

    # Setup meshtastic
    logging.info("Starting setup of Meshtastic")
    interface = setupMeshtastic(bleAddress, bleInterval)
    logging.info(f"Finished setup of Meshtastic")

    # Loop forever
    logging.info("Running application; waiting for messages from the radio")
    mqttClient.loop_forever()
    logging.info("Exiting; disconnected from the radio")


if __name__ == "__main__":
    main()
