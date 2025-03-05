# meshtastic2mqtt
Basic script to connect to a nRF node (e.g. RAK4631) and publish packets to MQTT

## Pair your node
```bash
BLEADDRESS=CF:B0:EF:3C:15:0A
bluetoothctl connect "$BLEADDRESS"
bluetoothctl pair "$BLEADDRESS"
bluetoothctl disconnect "$BLEADDRESS"
```

## Configure your node

Settings -> MQTT
* Enable MQTT
* Enable MQTT Client Proxy

## Running
I'm running this on an Raspberry Pi with only the basics installed.

Environmental options include:
* MESHTASTIC2MQTT_MQTT_HOST - Defaults to 'mqtt.davekeogh.com'
* MESHTASTIC2MQTT_MQTT_PORT - Defaults to '1883'
* MESHTASTIC2MQTT_MQTT_USERNAME - Defaults to 'meshdev'
* MESHTASTIC2MQTT_MQTT_PASSWORD" - Defaults to 'large4cats'
* MESHTASTIC2MQTT_MESHTASTIC_ADDRESS - Defaults to 'CF:B0:EF:3C:15:0A'

```
sudo docker run --detach --restart=always --privileged -v /run/dbus:/run/dbus:ro  ghcr.io/mannkind/meshtastic2mqtt:latest
```