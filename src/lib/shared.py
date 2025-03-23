LORA_MQTT_PUBSUB_TOPIC = "meshtastic2mqtt.publish"
APP_EXIT = "meshtastic2mqtt.exit"


class mqttOpts:
    """Class to hold the mqtt options."""

    def __init__(
        self,
        enabled: bool,
        proxy_to_client_enabled: bool,
        host: str,
        port: str,
        username: str,
        password: str,
    ) -> None:
        self.enabled = enabled
        self.proxy_to_client_enabled = proxy_to_client_enabled
        self.host = host
        self.port = port
        self.username = username
        self.password = password
