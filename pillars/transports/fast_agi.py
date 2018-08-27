import asyncio
import collections
import functools
import logging
from typing import Awaitable, Callable, Iterable, Optional

import panoramisk
from aiohttp.web_runner import BaseRunner

from ..request import BaseRequest

LOG = logging.getLogger(__name__)


async def middleware(
    request: "Request", handler: Callable[["FastAGIRequest"], Awaitable[None]]
) -> None:
    common_request = FastAGIRequest(request)
    await handler(common_request)


class Application(collections.MutableMapping):
    def __init__(self, middlewares: Optional[Iterable] = None) -> None:
        self.routes: dict = dict()
        self._state: dict = dict()

        if middlewares:
            middlewares = list(middlewares)
        else:
            middlewares = list()

        self._middlewares = middlewares

    async def shutdown(self) -> None:
        pass

    async def cleanup(self) -> None:
        pass

    async def _handler(self, request: "Request") -> None:
        request.app = self
        agi_network_script = request.get("agi_network_script")
        LOG.info(
            'Received FastAGI request from %r for "%s" route',
            request._transport.get_extra_info("peername"),
            agi_network_script,
        )

        if agi_network_script is not None:
            route = self.routes.get(agi_network_script)
            if route is not None:
                for m in reversed(self._middlewares):
                    route = functools.partial(m, handler=route)
                try:
                    await route(request)
                except Exception as e:
                    LOG.exception(e)
            else:
                LOG.error('No route for the request "%s"', agi_network_script)
        else:
            LOG.error("No agi_network_script header for the request")

        request.close()
        LOG.debug("Client socket closed")

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


class Request(collections.MutableMapping):
    def __init__(self, *, transport: asyncio.Transport, **kwargs) -> None:
        self.app: Optional[Application] = None
        self.hangup: bool = False

        self._state = kwargs
        self._futures: list = list()
        self._transport = transport

    async def send_command(self, command: str) -> dict:
        if not command.endswith("\n"):
            command += "\n"

        f: asyncio.Future = asyncio.Future()
        self._futures.append(f)
        self._transport.write(command.encode())
        return await f

    def _response(self, data: str) -> None:
        agi_result = panoramisk.utils.parse_agi_result(data)
        f = self._futures.pop()

        if "error" in agi_result:
            f.set_exception(FastAGIEException(agi_result))
        else:
            f.set_result(agi_result)

    def close(self) -> None:
        self._transport.close()

    def __repr__(self) -> str:
        return f"<FastAGI Request at 0x{id(self)}{' HANGUP' if self.hangup else ''}: {self._state}>"

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


class FastAGIRequest(BaseRequest):
    def __init__(self, request):
        super().__init__(request.app.state)
        self._request = request

    async def data(self) -> dict:
        return self._request._state

    @property
    def initial(self) -> Request:
        return self._request

    @property
    def config(self) -> dict:
        return dict()

    @property
    def method(self) -> None:
        return None

    @property
    def path(self) -> str:
        return self._request.get("agi_network_script", "")


class FastAGIEException(Exception):
    def __init__(self, data: dict) -> None:
        self.data = data


class AppRunner(BaseRunner):
    def __init__(self, app: Application) -> None:
        super().__init__()
        self._app = app

    async def shutdown(self) -> None:
        await self._app.shutdown()

    async def _make_server(self) -> "FastAGIServer":
        return FastAGIServer(self._app._handler)

    async def _cleanup_server(self) -> None:
        await self._app.cleanup()


class FastAGIServer:
    def __init__(self, handler: Callable[["Request"], Awaitable[None]]) -> None:
        self._handler = handler

    def __call__(self):
        return FastAGIProtocol(handler=self._handler)

    async def shutdown(self, timeout):
        pass


class FastAGIProtocol(asyncio.Protocol):
    def __init__(self, handler: Callable[["Request"], Awaitable[None]]) -> None:
        self._buffer = b""
        self._request: Optional[Request] = None
        self._handler = handler
        self._transport: Optional[asyncio.BaseTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport
        LOG.log(4, "connection made")

    def connection_lost(self, exc: Optional[Exception]) -> None:
        LOG.log(4, "connection lost")

    def data_received(self, raw_data: bytes) -> None:
        LOG.log(2, raw_data)

        if not self._request and b"\n\n" not in raw_data:
            self._buffer += raw_data
            return

        if not self._request:
            raw_data, self._buffer = self._buffer + raw_data, b""
            lines = raw_data.decode().split("\n")
            data: dict = dict(
                line.split(": ", 1) for line in lines if line  # type: ignore
            )
            LOG.log(4, data)
            self._request = Request(transport=self._transport, **data)  # type: ignore
            asyncio.ensure_future(self._handler(self._request))
        elif raw_data == b"HANGUP\n":
            self._request.hangup = True
        else:
            self._request._response(raw_data.decode())
