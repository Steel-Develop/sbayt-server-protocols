"""OPC UA server for signal values and source activity."""

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC
from time import monotonic
from typing import cast

from asyncua import ua
from asyncua.common.callback import CallbackType, ServerItemCallback
from asyncua.server.server import Server
from asyncua.ua.attribute_ids import AttributeIds
from asyncua.ua.status_codes import StatusCodes
from asyncua.ua.uaerrors import UaError
from asyncua.ua.uatypes import DateTime, UInt32

from sbayt_opcua_server.config import (
    DEFAULT_ENDPOINT,
    DEFAULT_NAMESPACE_URI,
    NodeConfig,
    parse_nodes,
)


@dataclass
class _SignalRuntime:
    node_id: ua.NodeId
    timeout: float
    data_type: str
    deadline: float | None = None


class OpcUaSignalServer:
    """Expose configured nodes as writable OPC UA variables."""

    def __init__(
        self,
        nodes: tuple[NodeConfig, ...] = (),
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        namespace_uri: str = DEFAULT_NAMESPACE_URI,
    ) -> None:
        self._nodes = nodes
        self._namespace_uri = namespace_uri
        self._server = Server()
        self._server.set_endpoint(endpoint)
        self._server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        self._server.set_identity_tokens([ua.AnonymousIdentityToken])
        self._runtime_by_id: dict[ua.NodeId, _SignalRuntime] = {}
        self._activity_changed = asyncio.Event()
        self._monitor_task: asyncio.Task[None] | None = None
        self._callbacks = {
            CallbackType.PreWrite: self._on_pre_write,
            CallbackType.PostWrite: self._on_post_write,
        }
        self._initialized = False
        self._namespace_index = 0
        self._registration_lock = asyncio.Lock()

    async def start(self) -> None:
        """Initialize nodes and begin listening for OPC UA clients."""
        await self._server.init()
        self._initialized = True
        try:
            self._namespace_index = await self._server.register_namespace(
                self._namespace_uri,
            )
            await self.ensure_nodes(self._nodes)
            await self._create_registration_method()
            await self._create_activity_method()
            for event, callback in self._callbacks.items():
                self._server.subscribe_server_callback(event, callback)
            await self._server.start()
            self._monitor_task = asyncio.create_task(self._monitor_inactivity())
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop the watchdog and close the OPC UA endpoint."""
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._monitor_task
            self._monitor_task = None
        for event, callback in self._callbacks.items():
            self._server.unsubscribe_server_callback(event, callback)
        if self._initialized:
            await self._server.stop()
            self._initialized = False
            self._runtime_by_id.clear()

    async def ensure_nodes(self, nodes: tuple[NodeConfig, ...]) -> None:
        """Register compatible nodes without resetting their values or activity."""
        async with self._registration_lock:
            for specification in nodes:
                node_id = ua.NodeId.from_string(specification.node_id)
                if node_id.NamespaceIndex != self._namespace_index:
                    raise ValueError(
                        f"NodeId {specification.node_id!r} uses namespace "
                        f"{node_id.NamespaceIndex}, but {self._namespace_uri!r} "
                        f"was registered as namespace {self._namespace_index}"
                    )
                existing = self._runtime_by_id.get(node_id)
                if existing and (
                    existing.data_type != specification.data_type
                    or existing.timeout != specification.inactivity_timeout_seconds
                ):
                    raise ValueError(
                        f"Incompatible definition for NodeId {specification.node_id!r}"
                    )
            await self._create_signal_nodes(nodes)

    async def _create_registration_method(self) -> None:
        async def ensure_nodes(
            _parent: ua.NodeId, argument: ua.Variant
        ) -> list[ua.Variant]:
            result: dict[str, object]
            try:
                if argument.VariantType != ua.VariantType.String or not isinstance(
                    argument.Value, str
                ):
                    raise ValueError("EnsureNodes requires a JSON string")
                nodes = parse_nodes(json.loads(argument.Value))
                await self.ensure_nodes(nodes)
                result = {"nodes": [node.node_id for node in nodes]}
            except (ValueError, UaError) as exc:
                result = {"error": str(exc)}
            return [ua.Variant(json.dumps(result), ua.VariantType.String)]

        await self._server.get_objects_node().add_method(
            1,
            "EnsureNodes",
            ensure_nodes,
            [ua.VariantType.String],
            [ua.VariantType.String],
        )

    async def _create_signal_nodes(self, nodes: tuple[NodeConfig, ...]) -> None:
        objects = self._server.get_objects_node()
        for specification in nodes:
            node_id = ua.NodeId.from_string(specification.node_id)
            if node_id in self._runtime_by_id:
                continue
            variant_type = ua.VariantType[specification.data_type]
            variable = await objects.add_variable(
                node_id,
                specification.name,
                ua.get_default_value(variant_type),
                varianttype=variant_type,
                datatype=variant_type.value,
            )
            await variable.set_writable()
            runtime = _SignalRuntime(
                node_id=node_id,
                timeout=specification.inactivity_timeout_seconds,
                data_type=specification.data_type,
            )
            self._runtime_by_id[node_id] = runtime
            await self._set_status(runtime, StatusCodes.BadWaitingForInitialData)

    async def _create_activity_method(self) -> None:
        async def set_signal_activity(
            _parent: ua.NodeId,
            node_id_argument: ua.Variant,
            active_argument: ua.Variant,
        ) -> list[ua.Variant]:
            if (
                node_id_argument.VariantType != ua.VariantType.NodeId
                or active_argument.VariantType != ua.VariantType.Boolean
            ):
                return [ua.Variant(False, ua.VariantType.Boolean)]
            node_id = cast(ua.NodeId, node_id_argument.Value)
            runtime = self._runtime_by_id.get(node_id)
            if runtime is None:
                return [ua.Variant(False, ua.VariantType.Boolean)]
            if not active_argument.Value:
                await self._set_status(runtime, StatusCodes.BadNoCommunication)
            return [ua.Variant(True, ua.VariantType.Boolean)]

        await self._server.get_objects_node().add_method(
            1,
            "SetSignalActivity",
            set_signal_activity,
            [ua.VariantType.NodeId, ua.VariantType.Boolean],
            [ua.VariantType.Boolean],
        )

    def _on_pre_write(
        self,
        event: ServerItemCallback,
        _callback_service: object,
    ) -> None:
        request = cast(ua.WriteParameters, event.request_params)
        for write in request.NodesToWrite:
            if (
                write.AttributeId != AttributeIds.Value
                or write.NodeId not in self._runtime_by_id
            ):
                continue
            value = write.Value
            timestamp = value.SourceTimestamp
            if (
                timestamp is None
                or timestamp.tzinfo is None
                or timestamp.utcoffset() is None
                or (value.StatusCode is not None and not value.StatusCode.is_good())
            ):
                write.Value = self._bad_value(
                    write.NodeId, StatusCodes.BadNoCommunication
                )
            else:
                write.Value = replace(
                    value,
                    SourceTimestamp=cast(DateTime, timestamp.astimezone(UTC)),
                    ServerTimestamp=DateTime.now(UTC),
                )

    def _on_post_write(
        self,
        event: ServerItemCallback,
        _callback_service: object,
    ) -> None:
        request = cast(ua.WriteParameters, event.request_params)
        results = cast(list[ua.StatusCode], event.response_params)
        for write, result in zip(request.NodesToWrite, results, strict=True):
            runtime = self._runtime_by_id.get(write.NodeId)
            if (
                runtime is None
                or write.AttributeId != AttributeIds.Value
                or not result.is_good()
            ):
                continue
            quality = write.Value.StatusCode
            runtime.deadline = (
                monotonic() + runtime.timeout
                if quality is None or quality.is_good()
                else None
            )
            self._activity_changed.set()

    async def _monitor_inactivity(self) -> None:
        while True:
            self._activity_changed.clear()
            deadlines = [
                runtime.deadline
                for runtime in self._runtime_by_id.values()
                if runtime.deadline is not None
            ]
            if not deadlines:
                await self._activity_changed.wait()
                continue

            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self._activity_changed.wait(), max(0, min(deadlines) - monotonic())
                )
            now = monotonic()
            for runtime in tuple(self._runtime_by_id.values()):
                if runtime.deadline is not None and runtime.deadline <= now:
                    await self._set_status(runtime, StatusCodes.BadNoCommunication)

    async def _set_status(
        self,
        runtime: _SignalRuntime,
        status_code: int,
    ) -> None:
        runtime.deadline = None
        self._activity_changed.set()
        await self._server.write_attribute_value(
            runtime.node_id, self._bad_value(runtime.node_id, status_code)
        )

    def _bad_value(self, node_id: ua.NodeId, status_code: int) -> ua.DataValue:
        return ua.DataValue(
            StatusCode=ua.StatusCode(UInt32(status_code)),
            SourceTimestamp=self._server.read_attribute_value(node_id).SourceTimestamp,
            ServerTimestamp=DateTime.now(UTC),
        )
