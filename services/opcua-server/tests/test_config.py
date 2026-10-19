import json
from pathlib import Path

import pytest

from sbayt_opcua_server.config import NodeConfig, load_nodes


def _write_config(tmp_path: Path, nodes: object) -> Path:
    path = tmp_path / "nodes.json"
    path.write_text(json.dumps({"nodes": nodes}), encoding="utf-8")
    return path


def test_given_valid_node_config_when_loading_then_returns_node_config(
    tmp_path: Path,
) -> None:
    path = _write_config(
        tmp_path,
        [
            {
                "node_id": "ns=02;s=temp",
                "data_type": "Double",
                "inactivity_timeout_seconds": 3,
            }
        ],
    )

    assert load_nodes(path) == (
        NodeConfig("ns=2;s=temp", "Double", "ns=2;s=temp", 3.0),
    )


@pytest.mark.parametrize("nodes", [[], None, {}, ["invalid"]])
def test_given_missing_or_malformed_nodes_when_loading_config_then_raises(
    tmp_path: Path, nodes: object
) -> None:
    with pytest.raises(ValueError):
        load_nodes(_write_config(tmp_path, nodes))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("node_id", "invalid"),
        ("node_id", None),
        ("data_type", "UNKNOWN"),
        ("name", ""),
        ("inactivity_timeout_seconds", 0),
        ("inactivity_timeout_seconds", True),
    ],
)
def test_given_invalid_node_fields_when_loading_config_then_raises(
    tmp_path: Path, field: str, value: object
) -> None:
    node = {
        "node_id": "ns=2;s=temp",
        "data_type": "Double",
        "inactivity_timeout_seconds": 3,
        field: value,
    }
    with pytest.raises(ValueError):
        load_nodes(_write_config(tmp_path, [node]))


def test_given_duplicate_physical_nodes_when_loading_config_then_raises(
    tmp_path: Path,
) -> None:
    node = {
        "node_id": "ns=2;s=temp",
        "data_type": "Double",
        "inactivity_timeout_seconds": 3,
    }
    with pytest.raises(ValueError, match="Duplicate"):
        load_nodes(_write_config(tmp_path, [node, {**node, "node_id": "ns=02;s=temp"}]))
