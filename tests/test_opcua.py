import asyncio
import json
from datetime import UTC, datetime

import pytest
from asyncua import Client, ua

pytestmark = pytest.mark.asyncio


async def test_given_opcua_image_when_registering_and_writing_then_preserves_protocol_and_expires(
    server,
    docker,
    wait_for_health,
):
    endpoint = f"opc.tcp://127.0.0.1:{server['port']}/signals"
    node_id = "ns=2;s=sample"
    declaration = {
        "node_id": node_id,
        "name": "sample",
        "data_type": "Double",
        "inactivity_timeout_seconds": 0.5,
    }
    async with Client(endpoint) as client:
        objects = client.get_objects_node()
        method = await objects.get_child(["1:EnsureNodes"])
        argument = json.dumps({"nodes": [declaration]})
        result = json.loads(await objects.call_method(method, argument))
        assert result == {"nodes": [node_id]}
        node = client.get_node(node_id)
        initial = await node.read_data_value(raise_on_bad_status=False)
        assert initial.StatusCode.value == ua.StatusCodes.BadWaitingForInitialData
        timestamp = datetime.now(UTC)
        await node.write_value(
            ua.DataValue(
                ua.Variant(23.5, ua.VariantType.Double), SourceTimestamp=timestamp
            )
        )
        current = await node.read_data_value()
        assert current.StatusCode.is_good()
        assert current.Value.Value == 23.5
        assert current.SourceTimestamp == timestamp
        assert json.loads(await objects.call_method(method, argument)) == result
        assert (await node.read_data_value()).Value.Value == 23.5
        await asyncio.sleep(0.7)
        expired = await node.read_data_value(raise_on_bad_status=False)
        assert expired.StatusCode.value == ua.StatusCodes.BadNoCommunication
        assert expired.Value.Value is None
        await node.write_value(
            ua.DataValue(
                ua.Variant(24.0, ua.VariantType.Double),
                SourceTimestamp=datetime.now(UTC),
            )
        )
        activity = await objects.get_child(["1:SetSignalActivity"])
        assert await objects.call_method(
            activity, ua.NodeId.from_string(node_id), False
        )
        assert (
            await node.read_data_value(raise_on_bad_status=False)
        ).StatusCode.is_bad()
    docker("restart", server["name"])
    wait_for_health(server["name"])
    binding = json.loads(docker("inspect", server["name"]))[0]["NetworkSettings"][
        "Ports"
    ]["4840/tcp"][0]
    endpoint = f"opc.tcp://127.0.0.1:{binding['HostPort']}/signals"
    async with Client(endpoint) as client:
        with pytest.raises(ua.UaStatusCodeError):
            await client.get_node(node_id).read_value()
