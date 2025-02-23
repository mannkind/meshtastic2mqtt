import logging
import sys
import os
import time
import threading
import meshtastic.ble_interface
from pubsub import pub
from meshtastic.protobuf import mqtt_pb2, config_pb2
import paho.mqtt.client as paho

LORA_MQTT_PUBSUB_TOPIC = "lopa2mqtt.publish"
APP_EXIT = "meshtastic2mqtt.exit"


def onMqttConnect(
    client: paho.Client, userdata, flags, reason_code, properties
) -> None:
    """Callback for when the MQTT client connects to the broker."""
    logging.info(f"Connected to MQTT; {reason_code}")


def onMqttDisconnect(
    client: paho.Client, userdata, flags, reason_code, properties
) -> None:
    """Callback for when the MQTT client disconnects from the broker."""
    logging.info(f"Disconnected from MQTT; {reason_code}")


def onMqttExit(client: paho.Client) -> None:
    """Callback for when the app exits"""
    logging.info("Exiting MQTT")
    client.disconnect()


def onMqttPublishRF(
    client: paho.Client,
    se: mqtt_pb2.ServiceEnvelope,
    topicBase: str,
    channelId: str,
    gatewayId: str,
) -> None:
    """Communication between the Meshtastic client and MQTT client."""
    client.publish(f"{topicBase}/{channelId}/{gatewayId}", se.SerializeToString())


def setupMQTT(
    mqttHost, mqttPort, mqttUsername, mqttPassword, mqttTopicBase
) -> paho.Client:
    """Sets up the MQTT client and subscribes to events."""
    client = paho.Client(paho.CallbackAPIVersion.VERSION2)
    client.on_connect = onMqttConnect
    client.on_disconnect = onMqttDisconnect
    client.username_pw_set(mqttUsername, mqttPassword)
    client.connect(mqttHost, mqttPort, 60)

    # Lora (RF) to MQTT communication channel
    pub.subscribe(
        onMqttPublishRF,
        LORA_MQTT_PUBSUB_TOPIC,
        client=client,
        topicBase=mqttTopicBase,
    )
    # Application exit communication channel
    pub.subscribe(onMqttExit, APP_EXIT, client=client)

    return client


def onMeshtasticConnect(
    interface: meshtastic.ble_interface.BLEInterface, rfBgThread: threading.Thread
) -> None:
    """Callback for when the Meshtastic client connects to the radio."""
    logging.info(f"Connected to Meshtastic")
    rfBgThread.start()


def onMeshtasticDisconnect(
    interface: meshtastic.ble_interface.BLEInterface,
) -> None:
    """Callback for when the Meshtastic client disconnects from the radio."""
    logging.info(f"Disconnected from Meshtastic")


def onMeshtasticExit(interface: meshtastic.ble_interface.BLEInterface) -> None:
    """Callback for when the app exits"""
    logging.info("Exiting Meshtastic")


def onMeshtasticReceive(
    packet,
    interface: meshtastic.ble_interface.BLEInterface,
    channelId: str,
    gatewayId: str,
) -> None:
    """Callback for when the Meshtastic client receives a packet from the radio."""
    logging.debug(f"{packet}\n\n")
    if "raw" not in packet or "decoded" not in packet:
        logging.info("Cannot get raw or decoded packet; skipping")
        return

    skipMqtt = (
        "decoded" in packet
        and "bitfield" in packet["decoded"]
        and packet["decoded"]["bitfield"] == 0
    )
    if skipMqtt:
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

    pub.sendMessage(
        LORA_MQTT_PUBSUB_TOPIC, se=se, channelId=channelId, gatewayId=gatewayId
    )


def fetchServiceEnvelopeDetails(
    interface: meshtastic.ble_interface.BLEInterface,
) -> tuple[str, str]:
    """Fetches the channel ID and gateway ID from the Meshtastic client."""
    node = interface.getNode("^local")
    modemPreset = node.localConfig.lora.modem_preset
    channelId = (
        config_pb2._CONFIG_LORACONFIG_MODEMPRESET.values_by_number[modemPreset]
        .name.title()
        .replace("_", "")
    )
    gatewayId = interface.getMyUser()["id"]

    return channelId, gatewayId


def checkMeshtasicRadio(
    interface: meshtastic.ble_interface.BLEInterface, interval: int
) -> None:
    """
    Determine if the radio is still connected and if not, exit the program by disconnecting from MQTT.
    This is a workaround for the fact that the Meshtastic library does not trigger a disconnect event on error
    """
    while True:
        try:
            logging.info("Sending heartbeat to the radio")
            interface.sendHeartbeat()
        except Exception as e:
            logging.error(f"Failed to send heartbeat; {e}")
            pub.sendMessage(APP_EXIT)
            break

        time.sleep(interval)

    return


def setupMeshtastic(bleAddress: str, interval: int) -> None:
    """ "Sets up the Meshtastic interface and subscribes to events."""
    try:
        interface = meshtastic.ble_interface.BLEInterface(bleAddress, noNodes=True)
    except Exception as e:
        logging.error(f"Failed to connect to the radio; {e}")
        sys.exit(1)

    channelId, gatewayId = fetchServiceEnvelopeDetails(interface)
    logging.info(
        f"Connected to the radio; channelId={channelId}, gatewayId={gatewayId}"
    )

    # Lora (RF) to MQTT communication channel
    pub.subscribe(
        onMeshtasticReceive,
        "meshtastic.receive",
        channelId=channelId,
        gatewayId=gatewayId,
    )

    # Meshtastic radio communication established; begin background thread to check radio connection
    rfBgThread = threading.Thread(
        target=lambda: checkMeshtasicRadio(interface, interval)
    )
    pub.subscribe(
        onMeshtasticConnect, "meshtastic.connection.established", rfBgThread=rfBgThread
    )

    # Meshtastic radio communication lost (does this work?)
    pub.subscribe(onMeshtasticDisconnect, "meshtastic.connection.lost")

    # Application exit communication channel
    pub.subscribe(onMeshtasticExit, APP_EXIT, interface=interface)

    return interface


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
