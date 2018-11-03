import asyncio
import collections
import logging
from typing import Awaitable, Callable
import functools
from aiohttp.web_runner import BaseRunner
from collections import defaultdict

from ..sites import dbus

LOG = logging.getLogger(__name__)


class AppRunner(BaseRunner):
    def __init__(self, app):
        super().__init__()
        self._app = app

    async def shutdown(self):
        await self._app.shutdown()

    async def _make_server(self):
        return DbusServer(self._app._handler)

    async def _cleanup_server(self):
        await self._app.cleanup()


class DbusServer:
    def __init__(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._handler = handler

    def __call__(self):
        return DbusProtocol(handler=self._handler)

    async def shutdown(self, timeout: int) -> None:
        pass


class DbusProtocol(dbus.DbusProtocol):
    def __init__(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._handler = handler

    def message_received(self, message, bus):
        signal = dbus.DbusSignal(
            bus=bus,
            interface=message.interface,
            path=tuple(message.path_decomposed),
            member=message.member,
            arguments=list(message.objects),
        )
        LOG.log(4, signal)
        asyncio.ensure_future(self._handler(signal))

    def connection_lost(self, exc):
        pass    


class Application(collections.MutableMapping):
    def __init__(self, app, middlewares=None) -> None:

        if middlewares:
            middlewares = list(middlewares)
        else:
            middlewares = []

        self.router = Router()
        self._state = collections.ChainMap({}, app)
        self._middlewares = middlewares

    async def shutdown(self):
        pass

    async def cleanup(self):
        pass

    async def _handler(self, signal):
        route = self.router.resolve(signal)
        if route:
            for middleware in reversed(self._middlewares):
                route = functools.partial(middleware, handler=route)
            try:
                await route(signal)
            except Exception as e:
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

    def add(self, handler, interface, path=None, member=None):
        self._routes[interface][(path, member)] = handler

    def resolve(self, signal):
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
