import logging
import subprocess
import sys
import time
import threading
from lib.shared import ALLOWED_PORT_NUMS, APP_EXIT, LORA_MQTT_PUBSUB_TOPIC
import meshtastic.ble_interface
from pubsub import pub
from meshtastic.protobuf import mqtt_pb2, config_pb2, channel_pb2

class publishingState:
    setupTime: int = 0
    waitBeforePublishing: int = 37
    enabled: bool = False

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
    packet,
    interface: meshtastic.ble_interface.BLEInterface,
    gatewayId: str,
    channels: dict[int, str],
) -> None:
    """Callback for when the Meshtastic client receives a packet from the radio."""
    global publishingState

    logging.debug(f"{packet}\n\n")
    if "raw" not in packet or "decoded" not in packet:
        logging.info("Cannot get raw or decoded packet; skipping")
        return

    if packet["decoded"]["portnum"] not in ALLOWED_PORT_NUMS:
        logging.info(f"Skipping {packet['decoded']['portnum']}")
        return

    # Map the channel index to a channel name
    channelIdx = 0
    if "channel" in packet:
        channelIdx = packet["channel"]

    if channelIdx not in channels:
        logging.info(
            f"Received {packet['decoded']['portnum']} on unknown channel {channelIdx}"
        )
        return

    skipMqtt = (
        "decoded" in packet
        and "bitfield" in packet["decoded"]
        and packet["decoded"]["bitfield"] == 0
    )
    if skipMqtt:
        logging.info(
            f"Received {packet['decoded']['portnum']} on {channels[channelIdx]}; does not want to be published to MQTT"
        )
        return

    logging.info(
        f"Received {packet['decoded']['portnum']} on {channels[channelIdx]} from the radio; republishing on MQTT"
    )
    mp = packet["raw"]
    se = mqtt_pb2.ServiceEnvelope()
    se.packet.CopyFrom(mp)
    se.channel_id = channels[channelIdx]
    se.gateway_id = gatewayId

    # Wait a bit before publishing to dump any enqueued/old packets
    if not publishingState.enabled:
        now = time.time()
        diff = now - publishingState.setupTime
        if diff < publishingState.waitBeforePublishing:
            logging.info(
                f"MQTT publishing disabled; waiting {int(publishingState.waitBeforePublishing - diff)}s"
            )
            return
        else:
            publishingState.enabled = True
            logging.info("MQTT publishing enabled")


    pub.sendMessage(LORA_MQTT_PUBSUB_TOPIC, se=se.SerializeToString(), channelId=se.channel_id, gatewayId=se.gateway_id)


def fetchServiceEnvelopeDetails(
    interface: meshtastic.ble_interface.BLEInterface,
) -> tuple[str, str]:
    """Fetches the channel ID and gateway ID from the Meshtastic client."""
    node = interface.getNode("^local")
    modemPreset = node.localConfig.lora.modem_preset
    gatewayId = interface.getMyUser()["id"]
    defaultChannelName = (
        config_pb2._CONFIG_LORACONFIG_MODEMPRESET.values_by_number[modemPreset]
        .name.title()
        .replace("_", "")
    )
    channels: dict[int, str] = {}
    for channel in node.channels:
        idx = channel.index
        if channel.role == channel_pb2.Channel.Role.DISABLED:
            continue

        if not channel.settings.uplink_enabled:
            continue

        name = channel.settings.name
        if name == "" and channel.role == channel_pb2.Channel.Role.PRIMARY:
            name = defaultChannelName

        channels[idx] = name

    return gatewayId, channels


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
        subprocess.run(["bluetoothctl", "disconnect", bleAddress], capture_output=False, check=True)
    except Exception as e:
        logging.error(f"Failed to disconnect from the radio; {e}")

    time.sleep(sleepBeforeConnectionAttempt)

    try:
        interface = meshtastic.ble_interface.BLEInterface(bleAddress, noNodes=True)
    except Exception as e:
        logging.error(f"Failed to connect to the radio; {e}")
        sys.exit(1)

    gatewayId, channels = fetchServiceEnvelopeDetails(interface)
    logging.info(f"Connected to the radio; gatewayId={gatewayId}")

    # Lora (RF) to MQTT communication channel
    pub.subscribe(
        onMeshtasticReceive,
        "meshtastic.receive",
        gatewayId=gatewayId,
        channels=channels,
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
