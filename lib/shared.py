from meshtastic.protobuf import portnums_pb2

LORA_MQTT_PUBSUB_TOPIC = "lopa2mqtt.publish"
APP_EXIT = "meshtastic2mqtt.exit"
ALLOWED_PORT_NUMS = set(
    [
        portnums_pb2.PortNum.Name(portnums_pb2.PortNum.NODEINFO_APP),
        portnums_pb2.PortNum.Name(portnums_pb2.PortNum.TEXT_MESSAGE_APP),
        portnums_pb2.PortNum.Name(portnums_pb2.PortNum.POSITION_APP),
        portnums_pb2.PortNum.Name(portnums_pb2.PortNum.TELEMETRY_APP),
        portnums_pb2.PortNum.Name(portnums_pb2.PortNum.MAP_REPORT_APP),
    ]
)