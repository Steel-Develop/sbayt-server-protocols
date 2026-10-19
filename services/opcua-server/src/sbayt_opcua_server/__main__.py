"""Run the standalone OPC UA server from generic node configuration."""

import asyncio
import logging
import os
import signal
from contextlib import suppress
from pathlib import Path

from sbayt_opcua_server.config import (
    DEFAULT_ENDPOINT,
    load_nodes,
)
from sbayt_opcua_server.server import OpcUaSignalServer


async def _serve() -> None:
    config_file = os.environ.get("OPCUA_CONFIG_FILE")
    nodes = load_nodes(Path(config_file)) if config_file else ()
    server = OpcUaSignalServer(nodes)
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(shutdown_signal, shutdown.set)

    await server.start()
    logging.getLogger(__name__).info(
        "Serving %d OPC UA nodes at %s", len(nodes), DEFAULT_ENDPOINT
    )
    try:
        await shutdown.wait()
    finally:
        await server.stop()


def main() -> None:
    """Serve nodes until interrupted."""
    logging.basicConfig(level=logging.INFO)
    with suppress(KeyboardInterrupt):
        asyncio.run(_serve())


if __name__ == "__main__":
    main()
