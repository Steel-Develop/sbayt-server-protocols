"""Load the server's generic JSON node configuration."""

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from asyncua import ua
from asyncua.ua.uaerrors import UaStringParsingError

DEFAULT_ENDPOINT = "opc.tcp://0.0.0.0:4840/signals"
DEFAULT_NAMESPACE_URI = "urn:sbayt:opcua:signals"
DATA_TYPES = ("Boolean", "Int32", "Int64", "Float", "Double", "String", "DateTime")


@dataclass(frozen=True)
class NodeConfig:
    node_id: str
    data_type: str
    name: str
    inactivity_timeout_seconds: float


def load_nodes(path: Path) -> tuple[NodeConfig, ...]:
    """Validate nodes before the server starts listening."""
    return parse_nodes(json.loads(path.read_text(encoding="utf-8")))


def parse_nodes(document: object) -> tuple[NodeConfig, ...]:
    """Validate the node declarations shared by files and remote registration."""
    nodes = document.get("nodes") if isinstance(document, dict) else None
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("Configuration must contain a non-empty nodes list")

    resolved = []
    seen = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError(f"Node at index {index} must be an object")
        raw_node_id = node.get("node_id")
        if not isinstance(raw_node_id, str) or not raw_node_id.strip():
            raise ValueError(f"Node at index {index} requires a node_id")
        try:
            node_id = ua.NodeId.from_string(raw_node_id).to_string()
        except (ValueError, UaStringParsingError) as exc:
            raise ValueError(f"Invalid OPC UA NodeId {raw_node_id!r}") from exc
        if node_id in seen:
            raise ValueError(f"Duplicate OPC UA NodeId {node_id!r}")
        data_type = node.get("data_type")
        if data_type not in DATA_TYPES:
            raise ValueError(
                f"Node {node_id!r} has unsupported data_type {data_type!r}"
            )
        name = node.get("name", node_id)
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Node {node_id!r} requires a non-empty name")
        timeout = node.get("inactivity_timeout_seconds")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError(f"Node {node_id!r} requires a positive finite timeout")
        seen.add(node_id)
        resolved.append(NodeConfig(node_id, data_type, name, float(timeout)))
    return tuple(resolved)
