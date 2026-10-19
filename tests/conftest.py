"""Shared Docker lifecycle for protocol image tests."""

import json
import os
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def docker():
    def run(*arguments: str) -> str:
        result = subprocess.run(
            ["docker", *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if arguments[0] == "logs":
            return (result.stdout + result.stderr).strip()
        return result.stdout.strip()

    return run


@pytest.fixture(scope="module")
def wait_for_health(docker):
    def wait(name: str) -> None:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = json.loads(docker("inspect", name))[0]["State"]
            if state.get("Health", {}).get("Status") == "healthy":
                return
            if not state["Running"]:
                break
            time.sleep(0.2)
        state = json.loads(docker("inspect", name))[0]["State"]
        pytest.fail(
            f"Container did not become healthy: {json.dumps(state)}\n"
            f"Container logs:\n{docker('logs', name)}"
        )

    return wait


@pytest.fixture(scope="module")
def server(docker, wait_for_health) -> Iterator[dict]:
    image = os.environ.get("SERVER_IMAGE")
    if not image:
        pytest.skip("Requires a built server image")
    catalog = Path(__file__).resolve().parents[1] / "services.json"
    definition = next(
        item
        for item in json.loads(catalog.read_text())
        if item["name"] == os.environ["SERVER_PROTOCOL"]
    )
    name = f"protocol-test-{uuid.uuid4().hex[:12]}"
    platform = os.environ.get("SERVER_PLATFORM")
    try:
        docker(
            "run",
            "--detach",
            "--pull",
            "never",
            "--name",
            name,
            *(["--platform", platform] if platform else []),
            "--publish",
            f"127.0.0.1::{definition['port']}",
            image,
        )
        wait_for_health(name)
        inspected = json.loads(docker("inspect", name))[0]
        binding = inspected["NetworkSettings"]["Ports"][f"{definition['port']}/tcp"][0]
        port = int(binding["HostPort"])
        assert port > 0
        yield {"name": name, "port": port}
    finally:
        subprocess.run(
            ["docker", "rm", "--force", "--volumes", name],
            capture_output=True,
            check=False,
            timeout=30,
        )
