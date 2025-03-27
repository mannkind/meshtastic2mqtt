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
    bleInterval = int(os.environ.get("MESHTASTIC2MQTT_MESHTASTIC_INTERVAL", "307"))
    bleAddress = os.environ.get(
        "MESHTASTIC2MQTT_MESHTASTIC_ADDRESS", "CF:B0:EF:3C:15:0A"
    )

    # Setup meshtastic
    logging.info("Starting setup of Meshtastic")
    interface, mqttOpts = setupMeshtastic(bleAddress, bleInterval)
    logging.info(f"Finished setup of Meshtastic")

    if not mqttOpts.enabled or not mqttOpts.proxy_to_client_enabled:
        logging.info("MQTT is not enabled on the radio; exiting")
        sys.exit(0)

    # Setup environment variables
    mqttHost = os.environ.get("MESHTASTIC2MQTT_MQTT_HOST", mqttOpts.host)
    mqttPort = int(os.environ.get("MESHTASTIC2MQTT_MQTT_PORT", mqttOpts.port))
    mqttUsername = os.environ.get("MESHTASTIC2MQTT_MQTT_USERNAME", mqttOpts.username)
    mqttPassword = os.environ.get("MESHTASTIC2MQTT_MQTT_PASSWORD", mqttOpts.password)

    # Setup MQTT
    logging.info("Starting setup of MQTT")
    mqttClient = setupMQTT(mqttHost, mqttPort, mqttUsername, mqttPassword)
    logging.info("Finished setup of MQTT")

    # Loop forever
    logging.info("Running application; waiting for messages from the radio")
    mqttClient.loop_forever()
    logging.info("Exiting; disconnected from the radio")


if __name__ == "__main__":
    main()
