import asyncio
import collections
import functools
import logging
from collections import defaultdict
from typing import Awaitable, Callable, Iterable, Optional, Tuple

import dbussy
from aiohttp.web_runner import BaseRunner

from ..app import Application as MainApplication
from ..sites import dbus

LOG = logging.getLogger(__name__)


class AppRunner(BaseRunner):
    def __init__(self, app: "Application") -> None:
        super().__init__()
        self._app = app

    async def shutdown(self) -> None:
        await self._app.shutdown()

    async def _make_server(self) -> "DbusServer":
        return DbusServer(self._app._handler)

    async def _cleanup_server(self) -> None:
        await self._app.cleanup()


class DbusServer:
    def __init__(self, handler: Callable[[dbus.DbusSignal], Awaitable[None]]) -> None:
        self._handler = handler

    def __call__(self) -> "DbusProtocol":
        return DbusProtocol(handler=self._handler)

    async def shutdown(self, timeout: int) -> None:
        pass


class DbusProtocol(dbus.DbusProtocol):
    def __init__(self, handler: Callable[[dbus.DbusSignal], Awaitable[None]]) -> None:
        self._handler = handler

    def message_received(self, message: dbussy.Message, bus: dbussy.Connection) -> None:
        signal = dbus.DbusSignal(
            bus=bus,
            interface=message.interface,
            path=tuple(message.path_decomposed),
            member=message.member,
            arguments=list(message.objects),
        )
        asyncio.ensure_future(self._handler(signal))

    def connection_lost(self, eror: Optional[Exception]) -> None:
        pass


class Application(collections.MutableMapping):
    def __init__(
        self, app: MainApplication, middlewares: Optional[Iterable] = None
    ) -> None:

        if middlewares:
            middlewares = list(middlewares)
        else:
            middlewares = []

        self.router = Router()
        self._state = collections.ChainMap({}, app)
        self._middlewares = middlewares

    async def shutdown(self) -> None:
        pass

    async def cleanup(self) -> None:
        pass

    async def _handler(self, signal: dbus.DbusSignal) -> None:
        LOG.debug("Handling: %s", signal)
        route = self.router.resolve(signal)
        if route:
            for middleware in reversed(self._middlewares):
                route = functools.partial(middleware, handler=route)
            try:
                await route(signal)
            except Exception:
                LOG.exception("Exception while handling signal: %s ", signal)

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


class Router:
    def __init__(self):
        self._routes = defaultdict(dict)

    def add(
        self,
        handler: Callable[[dbus.DbusSignal], Awaitable[None]],
        interface: str,
        path: Tuple[str] = None,
        member: str = None,
    ) -> None:
        self._routes[interface][(path, member)] = handler

    def resolve(
        self, signal: dbus.DbusSignal
    ) -> Optional[Callable[[dbus.DbusSignal], Awaitable[None]]]:
        try:
            return self._routes[signal.interface][(signal.path, signal.member)]
        except KeyError:
            pass

        try:
            return self._routes[signal.interface][(signal.path, None)]
        except KeyError:
            pass

        try:
            return self._routes[signal.interface][(None, signal.member)]
        except KeyError:
            pass

        try:
            return self._routes[signal.interface][(None, None)]
        except KeyError:
            pass

        return None
