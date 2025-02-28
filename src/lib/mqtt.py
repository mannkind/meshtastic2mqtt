import logging
from lib.shared import APP_EXIT, LORA_MQTT_PUBSUB_TOPIC
from pubsub import pub
import paho.mqtt.client as paho


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
    se: str,
    channelId: str,
    gatewayId: str,
    topicBase: str,
) -> None:
    """Communication between the Meshtastic client and MQTT client."""
    client.publish(f"{topicBase}/{channelId}/{gatewayId}", se)


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
