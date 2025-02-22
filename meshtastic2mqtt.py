import logging
import sys
import os
import atexit
import meshtastic.ble_interface
from pubsub import pub
from meshtastic.protobuf import mqtt_pb2, config_pb2
import paho.mqtt.client as paho


def onMQTTConnect(
    client: paho.Client, userdata, flags, reason_code, properties
) -> None:
    """Callback for when the MQTT client connects to the broker."""
    print(f"Connected to MQTT; {reason_code}")


def onMeshtasticConnect(interface: meshtastic.ble_interface.BLEInterface) -> None:
    """Callback for when the Meshtastic client connects to the radio."""
    print(f"Connected to Meshtastic")


def fetchServiceEnvelopeDetails(
    interface: meshtastic.ble_interface.BLEInterface,
) -> tuple[str, str]:
    """Fetches the channel ID and gateway ID from the Meshtastic interface."""
    node = interface.getNode("^local")
    modemPreset = node.localConfig.lora.modem_preset
    channelId = (
        config_pb2._CONFIG_LORACONFIG_MODEMPRESET.values_by_number[modemPreset]
        .name.title()
        .replace("_", "")
    )
    gatewayId = interface.getMyUser()["id"]

    return channelId, gatewayId


def onMeshtasticReceive(
    packet,
    interface,
    channelId: str,
    gatewayId: str,
    topicBase: str,
    mqttClient: paho.Client,
) -> None:
    logging.debug(f"{packet}\n\n")
    if "raw" not in packet or "decoded" not in packet:
        logging.info("Cannot get raw or decoded packet; skipping")
        return

    if (
        "decoded" in packet
        and "bitfield" in packet["decoded"]
        and packet["decoded"]["bitfield"] == 0
    ):
        logging.info(
            f"Received {packet['decoded']['portnum']} from radio; does not want to be published to MQTT"
        )
        return

    logging.info(
        f"Received {packet['decoded']['portnum']} from the radio; republishing on MQTT"
    )
    mp = packet["raw"]
    se = mqtt_pb2.ServiceEnvelope()
    se.packet.CopyFrom(mp)
    se.channel_id = channelId
    se.gateway_id = gatewayId

    mqttClient.publish(f"{topicBase}/{channelId}/{gatewayId}", se.SerializeToString())


if __name__ == "__main__":
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
    bleAddress = os.environ.get(
        "MESHTASTIC2MQTT_MESHTASTIC_ADDRESS", "CF:B0:EF:3C:15:0A"
    )

    # Setup MQTT
    logging.info("Starting setup of MQTT")
    mqttClient = paho.Client(paho.CallbackAPIVersion.VERSION2)
    mqttClient.on_connect = onMQTTConnect
    mqttClient.username_pw_set(mqttUsername, mqttPassword)
    mqttClient.connect(mqttHost, mqttPort, 60)
    logging.info("Finished setup of MQTT")

    # Setup meshtastic
    logging.info("Starting setup of Meshtastic")
    try:
        interface = meshtastic.ble_interface.BLEInterface(bleAddress, noNodes=True)
    except Exception as e:
        logging.error(f"Failed to connect to the radio; {e}")
        mqttClient.disconnect()
        sys.exit(1)

    channelId, gatewayId = fetchServiceEnvelopeDetails(interface)
    pub.subscribe(
        onMeshtasticReceive,
        "meshtastic.receive",
        channelId=channelId,
        gatewayId=gatewayId,
        topicBase=mqttTopicBase,
        mqttClient=mqttClient,
    )
    pub.subscribe(onMeshtasticConnect, "meshtastic.connection.established")
    logging.info(f"Finished setup of Meshtastic; {channelId}, {gatewayId}")

    def cleanup():
        logging.info("Cleaning up")
        interface.close()
        mqttClient.disconnect()

    atexit.register(cleanup)

    mqttClient.loop_forever()
