import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import UTC, datetime

import pytest
from asyncua import Client, ua
from asyncua.common.node import Node
from asyncua.common.subscription import DataChangeNotif

from sbayt_opcua_server.config import NodeConfig
from sbayt_opcua_server.server import OpcUaSignalServer

pytestmark = pytest.mark.integration
NODE_ID = "ns=2;s=Double"
SOURCE_TIMESTAMP = datetime(2026, 10, 15, tzinfo=UTC)
TIMEOUT_SECONDS = 0.5
SIGNAL_VALUES = (
    (ua.VariantType.Boolean, True),
    (ua.VariantType.Int32, 42),
    (ua.VariantType.Int64, 2**40),
    (ua.VariantType.Float, 1.5),
    (ua.VariantType.Double, 2.5),
    (ua.VariantType.String, "sample"),
    (ua.VariantType.DateTime, SOURCE_TIMESTAMP),
)


@pytest.fixture
async def client(unused_tcp_port: int) -> AsyncIterator[Client]:
    endpoint = f"opc.tcp://127.0.0.1:{unused_tcp_port}/server-test"
    nodes = tuple(
        NodeConfig(
            f"ns=2;s={variant_type.name}",
            variant_type.name,
            variant_type.name,
            TIMEOUT_SECONDS,
        )
        for variant_type, _ in SIGNAL_VALUES
    )
    server = OpcUaSignalServer(endpoint=endpoint)
    await server.start()
    try:
        async with Client(endpoint) as connected:
            with pytest.raises(ua.UaStatusCodeError):
                await connected.get_node(NODE_ID).read_value()
            response = await _register(connected, [asdict(node) for node in nodes])
            assert "error" not in response
            yield connected
    finally:
        await server.stop()


async def _register(client: Client, nodes: list[dict]) -> dict:
    objects = client.get_objects_node()
    method = await objects.get_child(["1:EnsureNodes"])
    return json.loads(await objects.call_method(method, json.dumps({"nodes": nodes})))


async def test_given_registered_node_when_registering_again_then_preserves_reading_and_deadline(
    client: Client,
) -> None:
    node = client.get_node(NODE_ID)
    await _write(node, 2.0)
    previous = await node.read_data_value()
    declaration = asdict(
        NodeConfig(NODE_ID, "Double", "renamed alias", TIMEOUT_SECONDS)
    )
    assert await _register(client, [declaration]) == {"nodes": [NODE_ID]}
    assert await node.read_data_value() == previous
    await asyncio.sleep(TIMEOUT_SECONDS + 0.1)
    expired = await node.read_data_value(raise_on_bad_status=False)
    assert expired.StatusCode.value == ua.StatusCodes.BadNoCommunication


@pytest.mark.parametrize(
    "changes", [{"data_type": "Boolean"}, {"inactivity_timeout_seconds": 9.0}]
)
async def test_given_incompatible_node_batch_when_registering_then_creates_no_other_nodes(
    client: Client, changes: dict
) -> None:
    new = asdict(NodeConfig("ns=2;s=new", "Double", "new", 1.0))
    incompatible = {
        **asdict(NodeConfig(NODE_ID, "Double", "wrong", TIMEOUT_SECONDS)),
        **changes,
    }
    result = await _register(client, [new, incompatible])
    assert "Incompatible" in result["error"]
    with pytest.raises(ua.UaStatusCodeError):
        await client.get_node("ns=2;s=new").read_value()


async def test_given_concurrent_requests_when_registering_same_node_then_creates_one_node(
    client: Client,
) -> None:
    node_id = "ns=2;s=concurrent"
    declaration = asdict(NodeConfig(node_id, "Double", "concurrent", 1.0))
    results = await asyncio.gather(
        *[_register(client, [declaration]) for _ in range(4)]
    )
    assert all(result == {"nodes": [node_id]} for result in results)
    children = await client.get_objects_node().get_children()
    assert sum(child.nodeid.to_string() == node_id for child in children) == 1


async def test_given_expiring_node_when_registering_another_node_then_watchdog_keeps_running(
    unused_tcp_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    endpoint = f"opc.tcp://127.0.0.1:{unused_tcp_port}/server-test"
    server = OpcUaSignalServer(endpoint=endpoint)
    expiring = asyncio.Event()
    resume = asyncio.Event()
    set_status = server._set_status

    async def pause_expiry(runtime, status):
        await set_status(runtime, status)
        if (
            runtime.node_id.to_string() == NODE_ID
            and status == ua.StatusCodes.BadNoCommunication
        ):
            expiring.set()
            await resume.wait()

    monkeypatch.setattr(server, "_set_status", pause_expiry)
    await server.start()
    try:
        async with Client(endpoint) as connected:
            await _register(
                connected, [asdict(NodeConfig(NODE_ID, "Double", "first", 0.05))]
            )
            await _write(connected.get_node(NODE_ID), 1.0)
            await asyncio.wait_for(expiring.wait(), timeout=2)
            second_id = "ns=2;s=second"
            await _register(
                connected, [asdict(NodeConfig(second_id, "Double", "second", 0.05))]
            )
            second = connected.get_node(second_id)
            await _write(second, 2.0)
            resume.set()
            await asyncio.sleep(0.15)
            reading = await second.read_data_value(raise_on_bad_status=False)
            assert reading.StatusCode.value == ua.StatusCodes.BadNoCommunication
    finally:
        resume.set()
        await server.stop()


async def _write(node: Node, value: float) -> None:
    await node.write_attribute(
        ua.AttributeIds.Value,
        ua.DataValue(
            ua.Variant(value, ua.VariantType.Double),
            SourceTimestamp=SOURCE_TIMESTAMP,
        ),
    )


async def _activate(client: Client, active: bool) -> None:
    objects = client.get_objects_node()
    method = await objects.get_child(["1:SetSignalActivity"])
    assert await objects.call_method(method, ua.NodeId.from_string(NODE_ID), active)


async def test_given_supported_types_and_timestamps_when_writing_then_reads_values_and_timestamps(
    client: Client,
) -> None:
    for variant_type, value in SIGNAL_VALUES:
        node = client.get_node(f"ns=2;s={variant_type.name}")
        initial = await node.read_data_value(raise_on_bad_status=False)
        assert initial.StatusCode.value == ua.StatusCodes.BadWaitingForInitialData
        assert initial.Value is None or initial.Value.Value is None

        await node.write_attribute(
            ua.AttributeIds.Value,
            ua.DataValue(
                ua.Variant(value, variant_type),
                SourceTimestamp=SOURCE_TIMESTAMP,
            ),
        )
        reading = await node.read_data_value()
        assert reading.StatusCode.is_good()
        assert reading.Value.VariantType == variant_type
        assert reading.Value.Value == value
        assert reading.SourceTimestamp == SOURCE_TIMESTAMP


@pytest.mark.parametrize("state", ["initial", "active", "inactive"])
async def test_given_incompatible_value_type_when_writing_then_rejects_and_preserves_reading(
    client: Client, state: str
) -> None:
    node = client.get_node(NODE_ID)
    if state != "initial":
        await _write(node, 1.0)
    if state == "inactive":
        await _activate(client, False)
    previous = await node.read_data_value(raise_on_bad_status=False)

    for variant in (
        ua.Variant("wrong", ua.VariantType.String),
        ua.Variant(True, ua.VariantType.Boolean),
        ua.Variant(42, ua.VariantType.Int64),
        ua.Variant(1.0, ua.VariantType.Float),
        ua.Variant(None, ua.VariantType.Null),
    ):
        with pytest.raises(ua.UaStatusCodeError) as raised:
            await node.write_attribute(
                ua.AttributeIds.Value,
                ua.DataValue(variant, SourceTimestamp=SOURCE_TIMESTAMP),
            )
        assert raised.value.code == ua.StatusCodes.BadTypeMismatch
        assert await node.read_data_value(raise_on_bad_status=False) == previous


class _Notifications:
    def __init__(self) -> None:
        self.values: asyncio.Queue[ua.DataValue] = asyncio.Queue()

    def datachange_notification(
        self, _node: Node, _value: object, data: DataChangeNotif
    ) -> None:
        self.values.put_nowait(data.monitored_item.Value)


@pytest.mark.parametrize(
    "quality", [None, ua.StatusCodes.BadNoCommunication, ua.StatusCodes.Uncertain]
)
async def test_given_invalid_timestamp_or_quality_when_writing_then_notifies_only_bad_quality(
    client: Client, quality: int | None
) -> None:
    node = client.get_node(NODE_ID)
    observer = _Notifications()
    subscription = await client.create_subscription(20, observer)
    try:
        await subscription.subscribe_data_change(node, queuesize=20)
        async with asyncio.timeout(3):
            await observer.values.get()  # Initial BadWaitingForInitialData.
            await _write(node, 1.0)
            valid = await observer.values.get()
            assert valid.StatusCode.is_good()

            invalid = ua.DataValue(ua.Variant(2.0, ua.VariantType.Double))
            if quality is not None:
                invalid = ua.DataValue(
                    invalid.Value,
                    StatusCode=ua.StatusCode(quality),
                    SourceTimestamp=SOURCE_TIMESTAMP,
                )
            await node.write_attribute(ua.AttributeIds.Value, invalid)
            notified = await observer.values.get()
        assert notified.StatusCode.value == ua.StatusCodes.BadNoCommunication
        assert notified.Value is None or notified.Value.Value is None
        assert await node.read_data_value(raise_on_bad_status=False) == notified
    finally:
        await subscription.delete()


async def test_given_signal_activity_changes_when_reactivating_then_requires_valid_write_to_restore_reading(
    client: Client,
) -> None:
    node = client.get_node(NODE_ID)
    await _activate(client, True)
    initial = await node.read_data_value(raise_on_bad_status=False)
    assert initial.StatusCode.value == ua.StatusCodes.BadWaitingForInitialData

    await _write(node, 1.0)
    await _activate(client, False)
    inactive = await node.read_data_value(raise_on_bad_status=False)
    assert inactive.StatusCode.value == ua.StatusCodes.BadNoCommunication
    assert inactive.Value is None or inactive.Value.Value is None
    assert inactive.SourceTimestamp == SOURCE_TIMESTAMP

    await _activate(client, True)
    assert await node.read_data_value(raise_on_bad_status=False) == inactive
    await _write(node, 2.0)
    assert await node.read_value() == 2.0


async def test_given_active_node_when_reactivating_without_write_then_preserves_expiry(
    client: Client,
) -> None:
    node = client.get_node(NODE_ID)
    await _write(node, 1.0)
    await _activate(client, True)

    async with asyncio.timeout(3):
        while (
            await node.read_data_value(raise_on_bad_status=False)
        ).StatusCode.is_good():
            await asyncio.sleep(0.01)

    expired = await node.read_data_value(raise_on_bad_status=False)
    assert expired.StatusCode.value == ua.StatusCodes.BadNoCommunication
    await _activate(client, True)
    assert await node.read_data_value(raise_on_bad_status=False) == expired
    await _write(node, 1.0)
    assert (await node.read_data_value()).StatusCode.is_good()


async def test_given_valid_and_invalid_values_when_writing_batch_then_reports_each_result(
    client: Client,
) -> None:
    node = client.get_node(NODE_ID)
    values = [
        ua.Variant(1.0, ua.VariantType.Double),
        ua.Variant("wrong", ua.VariantType.String),
    ]
    results = await client.uaclient.write(
        ua.WriteParameters(
            NodesToWrite=[
                ua.WriteValue(
                    NodeId=node.nodeid,
                    AttributeId=ua.AttributeIds.Value,
                    Value=ua.DataValue(value, SourceTimestamp=SOURCE_TIMESTAMP),
                )
                for value in values
            ]
        )
    )

    assert [result.value for result in results] == [
        ua.StatusCodes.Good,
        ua.StatusCodes.BadTypeMismatch,
    ]
    assert await node.read_value() == 1.0


async def test_given_constant_values_when_writing_repeatedly_then_keeps_signal_active(
    client: Client,
) -> None:
    node = client.get_node(NODE_ID)
    await _write(node, 1.0)
    for _ in range(3):
        await asyncio.sleep(TIMEOUT_SECONDS / 3)
        await _write(node, 1.0)
        assert await node.read_value() == 1.0
