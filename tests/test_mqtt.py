import subprocess
import time
import uuid

import pytest


def test_given_mqtt_image_when_publishing_then_delivers_payload_without_retention(
    server,
    docker,
):
    topic = f"protocol-test/{uuid.uuid4().hex}"
    payload = '{"value":23.5,"active":true}'
    arguments = [
        "docker",
        "exec",
        server["name"],
        "mosquitto_sub",
        "-h",
        "127.0.0.1",
        "-t",
        topic,
        "-q",
        "1",
        "-C",
        "1",
        "-F",
        "%r %p",
    ]
    subscriber = subprocess.Popen(
        arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        # Repeated publishes make subscription startup deterministic without guessing a sleep.
        for _ in range(20):
            docker(
                "exec",
                server["name"],
                "mosquitto_pub",
                "-h",
                "127.0.0.1",
                "-t",
                topic,
                "-q",
                "1",
                "-m",
                payload,
            )
            if subscriber.poll() is not None:
                break
            time.sleep(0.05)
        output, error = subscriber.communicate(timeout=5)
        assert subscriber.returncode == 0, error
        assert output.strip() == f"0 {payload}"
    finally:
        if subscriber.poll() is None:
            subscriber.kill()
            subscriber.communicate(timeout=5)
    subscriber = subprocess.Popen(
        arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            subscriber.communicate(timeout=0.5)
    finally:
        subscriber.kill()
        subscriber.communicate(timeout=5)
