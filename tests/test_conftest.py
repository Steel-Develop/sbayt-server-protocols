"""Regression tests for container startup and failure diagnostics."""

import json
import subprocess
from collections.abc import Callable
from unittest.mock import Mock

import conftest
import pytest


def test_given_slow_startup_when_waiting_then_allows_more_than_40_seconds(
    wait_for_health: Callable[[str], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Allow an emulated server to become healthy after the old deadline."""
    monkeypatch.setattr(conftest.time, "monotonic", Mock(side_effect=[0, 1, 41]))
    monkeypatch.setattr(conftest.time, "sleep", Mock())
    run = Mock(
        side_effect=[
            subprocess.CompletedProcess(
                ["docker", "inspect", "slow-server"],
                0,
                stdout=json.dumps(
                    [{"State": {"Running": True, "Health": {"Status": status}}}]
                ),
                stderr="",
            )
            for status in ("starting", "healthy")
        ]
    )
    monkeypatch.setattr(conftest.subprocess, "run", run)

    wait_for_health("slow-server")

    assert run.call_count == 2


@pytest.mark.parametrize("running", [True, False])
def test_given_failed_startup_when_waiting_then_reports_state_and_logs(
    wait_for_health: Callable[[str], None],
    monkeypatch: pytest.MonkeyPatch,
    running: bool,
) -> None:
    """Report healthcheck output and both log streams on exit or timeout."""
    monkeypatch.setattr(conftest.time, "monotonic", Mock(side_effect=[0, 1, 181]))
    monkeypatch.setattr(conftest.time, "sleep", Mock())
    state: dict[str, object] = {
        "Running": running,
        "ExitCode": 1,
        "Health": {
            "Status": "unhealthy",
            "Log": [{"Output": "connection refused"}],
        },
    }

    def run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        """Return inspect data or Docker's separate output streams."""
        output = json.dumps([{"State": state}])
        if arguments[1] == "logs":
            return subprocess.CompletedProcess(
                arguments, 0, stdout="server output\n", stderr="startup error\n"
            )
        return subprocess.CompletedProcess(arguments, 0, stdout=output, stderr="")

    monkeypatch.setattr(conftest.subprocess, "run", run)

    with pytest.raises(pytest.fail.Exception) as failure:
        wait_for_health("failed-server")

    message = str(failure.value)
    assert "connection refused" in message
    assert '"ExitCode": 1' in message
    assert "server output" in message
    assert "startup error" in message
