import asyncio
import dataclasses
import logging
from typing import Iterable, List, Optional, Tuple

import dbussy
from aiohttp.web_runner import BaseRunner, BaseSite

LOG = logging.getLogger(__name__)


@dataclasses.dataclass
class DbusSignal:
    member: str
    interface: str
    path: Tuple[str, ...]
    arguments: List[str]
    bus: dbussy.Connection = dataclasses.field(repr=False)


@dataclasses.dataclass
class DbusMatch:
    type_: str = "signal"
    member: Optional[str] = None
    interface: Optional[str] = None

    def serialize(self):
        rule = {"type": self.type_}
        if self.member:
            rule["member"] = self.member
        if self.interface:
            rule["interface"] = self.interface

        return dbussy.format_rule(rule)


class DbusTransport(asyncio.BaseTransport):
    def __init__(self, bus: dbussy.Connection, **kwargs) -> None:
        super().__init__(**kwargs)
        self._bus: dbussy.Connection = bus
        self._task: Optional[asyncio.Task] = None
        self._closing: bool = False

    def close(self) -> None:
        self._closing = True
        if self._bus:
            self._bus = None
        if self._task:
            self._task.cancel()

    async def closed(self) -> None:
        if self._closing and self._task:
            await self._task
            self._task = None

    async def _run(self, protocol: "DbusProtocol") -> None:
        try:
            async for message in self._bus.iter_messages_async():
                protocol.message_received(message, self._bus)
        except asyncio.CancelledError:
            protocol.connection_lost(None)
        except Exception as e:
            protocol.connection_lost(e)
        else:
            protocol.connection_lost(None)

    def is_closing(self):
        """Return True if the transport is closing or closed."""
        return self._closing

    def set_protocol(self, protocol):
        """Set a new protocol."""
        raise NotImplementedError

    def get_protocol(self):
        """Return the current protocol."""
        raise NotImplementedError


class DbusServer:
    """
    Shim to present a unified server interface.
    """

    def __init__(self, transport: DbusTransport) -> None:
        self.transport = transport

    def close(self) -> None:
        self.transport.close()

    async def wait_closed(self) -> None:
        await self.transport.closed()


class DbusProtocol(asyncio.BaseProtocol):
    def message_received(self, message: dbussy.Message, bus: dbussy.Connection) -> None:
        raise NotImplementedError()


class DbusSignalListener(BaseSite):
    def __init__(
        self,
        runner: BaseRunner,
        bus: Optional[int] = None,
        matches: Iterable[DbusMatch] = None,
        *,
        shutdown_timeout: float = 60.0,
    ) -> None:
        super().__init__(runner, shutdown_timeout=shutdown_timeout)

        if not bus:
            bus = dbussy.DBUS.BUS_SESSION

        if matches and not all(isinstance(math, DbusMatch) for math in matches):
            raise TypeError("Matches should be of type DbusMatch")
        elif not matches:
            matches = (DbusMatch(),)

        self._bus = None
        self._matches = matches
        self._bus_type = bus

    async def start(self) -> None:
        await super().start()

        bus = await dbussy.Connection.bus_get_async(self._bus_type, private=False)
        bus.enable_receive_message({dbussy.DBUS.MESSAGE_TYPE_SIGNAL})

        await asyncio.gather(
            *(bus.bus_add_match_async(match.serialize()) for match in self._matches)
        )

        transport = DbusTransport(bus=bus)
        protocol = self._runner.server()
        protocol.connection_made(transport)
        transport._task = asyncio.create_task(transport._run(protocol))
        self._server = DbusServer(transport=transport)

    async def stop(self) -> None:
        self._closing = True
        await super().stop()

    @property
    def name(self) -> str:
        return f"DBUS://{self._bus_type}?{self._matches}"
