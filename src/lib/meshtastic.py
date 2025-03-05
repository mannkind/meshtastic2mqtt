import logging
import subprocess
import sys
import time
import threading
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from lib.shared import APP_EXIT, LORA_MQTT_PUBSUB_TOPIC
import meshtastic.ble_interface
from pubsub import pub
from meshtastic.protobuf import (
    mesh_pb2,
    mqtt_pb2,
    channel_pb2,
    config_pb2,
    portnums_pb2,
)


class publishingState:
    """Class to hold the state of the publishing process."""

    setupTime: int = 0
    waitBeforePublishing: int = 37
    enabled: bool = False


class meshtasticChannel:
    """Class to hold the channel name and encryption key for a Meshtastic channel."""

    def __init__(self, name: str, key: bytes) -> None:
        self.name = name
        self.key = key


sleepBeforeConnectionAttempt = 10


def onMeshtasticConnect(
    interface: meshtastic.ble_interface.BLEInterface, rfBgThread: threading.Thread
) -> None:
    """Callback for when the Meshtastic client connects to the radio."""
    logging.info(f"Connected to Meshtastic")
    publishingState.setupTime = time.time()
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
    proxymessage,
    interface: meshtastic.ble_interface.BLEInterface,
    channels: dict[str, meshtasticChannel],
) -> None:
    """Callback for when the Meshtastic client receives a packet from the radio."""
    global publishingState

    _logOnMeshtasticReceive(proxymessage, channels)

    # Wait a bit before publishing to dump any enqueued/old packets
    if not publishingState.enabled:
        now = time.time()
        diff = now - publishingState.setupTime
        if diff < publishingState.waitBeforePublishing:
            logging.info(
                f"Publishing disabled; waiting an additional {int(publishingState.waitBeforePublishing - diff)}s"
            )
            return
        else:
            publishingState.enabled = True
            logging.info("Publishing enabled")

    pub.sendMessage(
        LORA_MQTT_PUBSUB_TOPIC, topic=proxymessage.topic, message=proxymessage.data
    )


def getChannelInfo(
    interface: meshtastic.ble_interface.BLEInterface,
) -> dict[str, meshtasticChannel]:
    """Fetches the channel ID and gateway ID from the Meshtastic client."""
    node = interface.getNode("^local")
    modemPreset = node.localConfig.lora.modem_preset
    defaultChannelName: str = (
        config_pb2._CONFIG_LORACONFIG_MODEMPRESET.values_by_number[modemPreset]
        .name.title()
        .replace("_", "")
    )

    channels: dict[str, meshtasticChannel] = {}
    for channel in node.channels:
        if channel.role == channel_pb2.Channel.Role.DISABLED:
            continue

        name = channel.settings.name
        psk: bytes = channel.settings.psk

        if name == "" and channel.role == channel_pb2.Channel.Role.PRIMARY:
            name = defaultChannelName
        if psk == b"\001" and channel.role == channel_pb2.Channel.Role.PRIMARY:
            psk = b"\xd4\xf1\xbb: )\x07Y\xf0\xbc\xff\xab\xcfNi\x01"

        channels[name] = meshtasticChannel(name, psk)

        if channel.role == channel_pb2.Channel.Role.PRIMARY:
            channels["default"] = channels[name]

    return channels


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
        subprocess.run(
            ["bluetoothctl", "disconnect", bleAddress], capture_output=False, check=True
        )
    except Exception as e:
        logging.error(f"Failed to disconnect from the radio; {e}")

    time.sleep(sleepBeforeConnectionAttempt)

    try:
        interface = meshtastic.ble_interface.BLEInterface(bleAddress, noNodes=True)
    except Exception as e:
        logging.error(f"Failed to connect to the radio; {e}")
        sys.exit(1)

    channels = getChannelInfo(interface)
    logging.info(f"Connected to the radio")

    # Meshtastic radio communication established; begin background thread to check radio connection
    rfBgThread = threading.Thread(
        target=lambda: checkMeshtasicRadio(interface, interval)
    )

    # Lora (RF) to MQTT communication channel
    pub.subscribe(
        onMeshtasticReceive, "meshtastic.mqttclientproxymessage", channels=channels
    )

    pub.subscribe(
        onMeshtasticConnect, "meshtastic.connection.established", rfBgThread=rfBgThread
    )

    # Meshtastic radio communication lost (does this work?)
    pub.subscribe(onMeshtasticDisconnect, "meshtastic.connection.lost")

    # Application exit communication channel
    pub.subscribe(onMeshtasticExit, APP_EXIT, interface=interface)

    return interface


def _logOnMeshtasticReceive(
    proxymessage, channels: dict[str, meshtasticChannel]
) -> None:
    se = mqtt_pb2.ServiceEnvelope()
    se.ParseFromString(proxymessage.data)
    packet = se.packet
    if packet.HasField("encrypted"):
        try:
            channelName = se.channel_id if se.channel_id in channels else "default"
            cipher = Cipher(
                algorithms.AES(channels[channelName].key),
                modes.CTR(
                    packet.id.to_bytes(8, "little")
                    + getattr(packet, "from").to_bytes(8, "little")
                ),
                backend=default_backend(),
            )
            decryptor = cipher.decryptor()
            bytes = decryptor.update(packet.encrypted) + decryptor.finalize()
            decoded = mesh_pb2.Data()
            decoded.ParseFromString(bytes)
            packet.decoded.CopyFrom(decoded)
        except Exception as e:
            logging.warning(f"Unable to decrypt packet; {e}")

    topic = proxymessage.topic
    portnum = "unknown"
    message = "encrypted"
    if packet.HasField("decoded"):
        portnum = portnums_pb2.PortNum.Name(packet.decoded.portnum)
        message = packet.decoded.payload

    logging.info(
        f"Received packet from Meshtastic\n\tTopic {topic}\n\tChannel: {se.channel_id}\n\tPortnum: {portnum}\n\tMessage: {message}\n\tSNR/RSSI: ({se.packet.rx_snr}dB/{se.packet.rx_rssi}dBm)"
    )
