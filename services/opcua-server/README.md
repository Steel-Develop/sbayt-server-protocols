# Sbayt OPC UA Server

A standalone OPC UA server for external signal writers. It registers requested
nodes and accepts values and source timestamps over OPC UA. It does not generate
measurements or require application SDKs, credentials, or simulation manifests.

This directory is a complete Python project and Docker build context. Its only
runtime dependency is the public asyncua package.

## Run

Requires Python 3.14 and uv. Run these commands from this directory:

```bash
uv sync --frozen
uv run python -m sbayt_opcua_server
```

The process starts empty. `OPCUA_CONFIG_FILE=examples/nodes.json` optionally loads
initial nodes for standalone development. It listens at
`opc.tcp://0.0.0.0:4840/signals`, using namespace URI `urn:sbayt:opcua:signals`.
Any OPC UA client can register nodes and write values. The server accepts generic
node declarations and does not require application-specific configuration.

## Registration contract

The Objects folder exposes `1:EnsureNodes` with one String input and one String
output, both containing JSON. Its input is:

```json
{
  "nodes": [
    {
      "node_id": "ns=2;s=temperature",
      "data_type": "Double",
      "name": "temperature",
      "inactivity_timeout_seconds": 3.0
    }
  ]
}
```

The `nodes` list must be non-empty. Each node requires a unique `node_id`, a
supported `data_type` and a positive finite timeout in seconds. The optional
`name` defaults to the NodeId. Supported types are `Boolean`, `Int32`, `Int64`,
`Float`, `Double`, `String` and `DateTime`. NodeIds are normalized before checking
uniqueness. Namespace index 2 is registered for the configured namespace URI;
other indices are rejected.

On success the result is `{"nodes": ["ns=2;s=temperature"]}`. Invalid declarations
or conflicting types/timeouts return `{"error": "..."}`. A batch is validated
before creating nodes, and concurrent registrations are serialized. Compatible
repeated registrations preserve values, quality and inactivity deadlines. Nodes
remain in memory until the server stops. The optional startup file uses the same
input document.

`DateTime` is a process value, separate from the sample's `SourceTimestamp`.
Writes need a timezone-aware source timestamp, normalized to UTC. Writes with a
valid source timestamp and Good quality but an incompatible type are rejected
with `BadTypeMismatch`, leaving the previous reading and deadline intact.
Missing timestamps and non-Good quality produce `BadNoCommunication`, before
any notification is sent to subscribers.

## Activity contract

Nodes start with `BadWaitingForInitialData`. Valid writes set quality to Good
and renew the node's inactivity timeout, including writes of constant values.
Expiry sets `BadNoCommunication`; a new valid write reactivates the node.

The Objects folder exposes `SetSignalActivity` with inputs NodeId and Boolean,
and a Boolean result indicating whether the node exists. Calling it with `false`
immediately sets `BadNoCommunication`. Calling it with `true` preserves an active
node's deadline and leaves inactive data Bad until the next valid write.
The method is browsable as `1:SetSignalActivity`.

Bad quality consistently returns a null value in reads and notifications, as
required by the [OPC UA DataValue contract](https://reference.opcfoundation.org/specs/OPC-10000-4/7.11.1).
The last accepted source timestamp is retained. Clients must inspect quality
before treating a value as a current measurement.

## Docker

Build and run from this directory; only public Python dependencies are needed:

```bash
docker build -t sbayt-opcua-server:local .
docker run --rm \
  -p 127.0.0.1:4840:4840 \
  sbayt-opcua-server:local
```

The endpoint has no authentication or encryption. Publish it only on the
required local or private interface. The container listens on port 4840;
choose a different published host port when running multiple servers.

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Tests start their own local OPC UA server and require no external services.
