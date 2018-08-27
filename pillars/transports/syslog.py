import asyncio
import collections
import logging
from typing import Awaitable, Callable, Optional, Tuple, Union

from aiohttp.web_runner import BaseRunner

LOG = logging.getLogger(__name__)


class Application(collections.MutableMapping):
    async def shutdown(self) -> None:
        pass

    async def cleanup(self) -> None:
        pass

    async def _handler(self, data: Union[str, bytes], addr: Tuple[str, int]) -> None:
        LOG.debug(data, addr)

    def __init__(self) -> None:
        self._state: dict = dict()

    # MutableMapping API
    def __eq__(self, other):
        return self is other

    def __getitem__(self, key):
        return self._state[key]

    def __setitem__(self, key, value):
        self._state[key] = value

    def __delitem__(self, key):
        del self._state[key]

    def __len__(self):
        return len(self._state)

    def __iter__(self):
        return iter(self._state)


class AppRunner(BaseRunner):
    def __init__(self, app: Application) -> None:
        super().__init__()
        self._app = app

    async def shutdown(self) -> None:
        await self._app.shutdown()

    async def _make_server(self) -> "SyslogServer":
        return SyslogServer(self._app._handler)

    async def _cleanup_server(self) -> None:
        await self._app.cleanup()


class SyslogServer:
    def __init__(
        self, handler: Callable[[Union[str, bytes], Tuple[str, int]], Awaitable[None]]
    ) -> None:
        self._handler = handler

    def __call__(self) -> "SyslogProtocol":
        return SyslogProtocol(handler=self._handler)

    async def shutdown(self, timeout) -> None:
        pass


class SyslogProtocol(asyncio.Protocol, asyncio.DatagramProtocol):
    def __init__(
        self, handler: Callable[[Union[str, bytes], Tuple[str, int]], Awaitable[None]]
    ) -> None:
        self._handler = handler
        self.transport: Optional[asyncio.BaseTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport

    def data_received(self, data: Union[str, bytes]) -> None:
        if self.transport:
            addr = self.transport.get_extra_info("peername")
        else:
            addr = ("", 0)

        asyncio.ensure_future(self._handler(data, addr))

    def datagram_received(self, data: Union[str, bytes], addr: Tuple[str, int]) -> None:
        asyncio.ensure_future(self._handler(data, addr))
