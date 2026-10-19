FROM eclipse-mosquitto:2

COPY mosquitto.conf /mosquitto/config/mosquitto.conf

HEALTHCHECK --interval=5s --timeout=3s --start-period=2s --retries=5 \
    CMD mosquitto_pub -h 127.0.0.1 -p 1883 -t _health/mqtt -n -q 1
