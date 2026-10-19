# Sbayt Server Protocols

Standalone protocol servers and Docker images. External clients create nodes or
publish messages; the servers expose only generic protocol behavior.

[Leer en español](README.es.md)

## Servers

| Server | Docker Hub image | Container port | Documentation |
| --- | --- | --- | --- |
| OPC UA | `sbayt1/sbayt-opcua-server` | 4840 | [Node registration, writes and activity](services/opcua-server/README.md) |
| MQTT | `sbayt1/sbayt-mqtt-server` | 1883 | [Mosquitto configuration](services/mqtt-server/README.md) |

Images share release versions. Release `v0.1.0` publishes tag `0.1.0` for each
server; `latest` is promoted after both published images pass verification.
Both images target `linux/amd64` and `linux/arm64`. Image availability begins
with the first successful release publication.

## Run published images

```bash
docker run --rm --name opcua -p 127.0.0.1:4840:4840 sbayt1/sbayt-opcua-server:latest
docker run --rm --name mqtt -p 127.0.0.1:1883:1883 sbayt1/sbayt-mqtt-server:latest
```

The OPC UA endpoint is `opc.tcp://127.0.0.1:4840/signals`. It starts empty and
accepts generic node declarations through `1:EnsureNodes` before a client writes
values. `1:SetSignalActivity` and configurable inactivity timeouts expose source
availability through OPC UA quality codes.

The MQTT broker listens on port 1883 and routes the publishers' payloads to
subscribers. It does not persist data to disk. Both default servers accept
anonymous connections without encryption; the examples bind to host loopback.

## Build locally

Each service directory is a complete Docker build context:

```bash
docker build -t sbayt-opcua-server:local services/opcua-server
docker build -t sbayt-mqtt-server:local services/mqtt-server
```

Use those local image names in the run commands above before publication.
Existing protocol contracts and dependency versions are preserved when moving
or building either service independently.

## Development and validation

Python 3.14 and uv are required for OPC UA development and the image tests.
All Python dependencies are resolved from public PyPI. The root project provides
independent tooling for image tests. Only OPC UA checks install its client library;
MQTT checks use the clients included in the broker image.

```bash
uv sync --locked
uv sync --project services/opcua-server --locked --all-groups
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --project services/opcua-server mypy --config-file services/opcua-server/pyproject.toml services/opcua-server/src
uv run --project services/opcua-server pytest services/opcua-server/tests
```

After building the images, test actual containers and their protocol contracts:

```bash
SERVER_PROTOCOL=opcua SERVER_IMAGE=sbayt-opcua-server:local \
  uv run --locked --group opcua pytest tests/test_opcua.py
SERVER_PROTOCOL=mqtt SERVER_IMAGE=sbayt-mqtt-server:local \
  uv run --locked --group mqtt pytest tests/test_mqtt.py
```

The checks use temporary containers and random loopback ports. They verify
health, OPC UA registration/writes/expiry/restart, and MQTT delivery without
retention. They remove their own containers and anonymous volumes afterwards.
Set `SERVER_PLATFORM=linux/arm64` to test an ARM image on a Docker host with the
corresponding execution support. Test names use `test_given_when_then`.

## Add a server

1. Add an autonomous directory under `services/`, with its Dockerfile,
   configuration, healthcheck, documentation and any source-specific tests.
2. Add its name, context, Docker Hub image and container port to `services.json`.
   CI, version publication and `latest` promotion use this shared catalog.
3. Add `tests/test_<name>.py` and a matching dependency group in the root
   `pyproject.toml` (empty if no additional client is needed). The shared fixture
   checks container health. Add source checks to CI if another toolchain is needed.
4. Add the service to both README tables and create its public Docker Hub repository.

The repository contains generic protocol infrastructure. Application models,
client-specific transformations and deployment orchestration belong to consumers.

## Publishing

CI validates source and Docker images on pull requests and `master`. Publishing
a stable GitHub release with a tag such as `v0.1.0` runs CI again, publishes both
versioned images, checks anonymous pulls and both architectures, then promotes
those manifests to `latest`. No registry credentials are passed to PR checks.

See [GitHub and Docker Hub setup](docs/publishing.md) for manual configuration.
The release tag defines the shared Docker image version; the OPC UA Python
package is not published separately.

## License

[MIT](LICENSE) for this repository's code and configuration. Container base
images and dependencies retain their respective licenses.
