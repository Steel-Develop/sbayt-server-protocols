# MQTT broker

Standalone Mosquitto distribution. This directory is its complete Docker build
context; it contains the broker configuration and image healthcheck.

```bash
docker build -t sbayt-mqtt-server:local .
docker run --rm --name mqtt -p 127.0.0.1:1883:1883 sbayt-mqtt-server:local
```

The image extends [Eclipse Mosquitto](https://github.com/eclipse-mosquitto/mosquitto/tree/master/docker)
with a listener on port 1883, anonymous connections, logs on stdout and disabled
disk persistence. Its healthcheck publishes an empty, non-retained MQTT message
to `_health/mqtt` with QoS 1. Data publishers should use their own topics.

The bundled configuration is for local development. For clients on other hosts,
publish a reachable host interface. Custom authentication or TLS requires a
different Mosquitto configuration; the default listener uses plain MQTT.

Subscribers receive payloads supplied by external publishers. Retention follows
the MQTT retain flag chosen by each publisher. Disconnecting a publisher leaves
the broker running.
