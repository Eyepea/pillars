import asyncio
import collections
import functools
import logging
from typing import Awaitable, Callable, Iterable, Optional, Tuple, Union

import aiohttp.http_websocket
from aiohttp.web_runner import BaseRunner
import ujson

from ..app import Application as MainApplication
from ..request import BaseRequest
from ..sites.websocket import WSProtocol

LOG = logging.getLogger(__name__)


class AppRunner(BaseRunner):
    def __init__(self, app: "Application") -> None:
        super().__init__()
        self._app = app

    async def shutdown(self) -> None:
        await self._app.shutdown()

    async def _make_server(self) -> "AriServer":
        return AriServer(self._app._handler)

    async def _cleanup_server(self) -> None:
        await self._app.cleanup()


class Event:
    def __init__(self, app, config, data):
        self.app = app
        self.data = data
        self.config = config

    @property
    def type(self):
        return self.data["type"].lower()


class Application(collections.MutableMapping):
    def __init__(
        self, app: MainApplication, middlewares: Optional[Iterable] = None
    ) -> None:

        if middlewares:
            middlewares = list(middlewares)
            middlewares.insert(0, middleware)
        else:
            middlewares = (middleware,)

        self.router = Router()
        self._state = collections.ChainMap({}, app)
        self._middlewares = middlewares

    async def shutdown(self) -> None:
        pass

    async def cleanup(self) -> None:
        pass

    async def _handler(self, data: dict) -> None:

        route, config = self.router.resolve(data["type"].lower())
        if route:
            event = Event(app=self, config=config, data=data)
            await self._call_route(route, event)
            return

        LOG.debug("No route for event: %s", data["type"])

    async def _call_route(
        self, route: Callable[[Event], Awaitable[None]], event: Event
    ) -> None:
        LOG.log(4, "Handling event: %s", event.type)
        for middleware in reversed(self._middlewares):
            route = functools.partial(middleware, handler=route)
        try:
            await route(event)
        except Exception as e:
            LOG.exception("Exception while handling event: %s ", event)

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


class AriServer:
    def __init__(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._handler = handler

    def __call__(self) -> "AriProtocol":
        return AriProtocol(handler=self._handler)

    async def shutdown(self, timeout: int) -> None:
        pass


class AriProtocol(WSProtocol):
    def __init__(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._handler = handler

    def message_received(
        self,
        message_type: aiohttp.http_websocket.WSMsgType,
        data: Union[str, bytes, aiohttp.http_websocket.WSCloseCode],
        extra: str,
    ):
        LOG.log(2, "Message received: %s %s", message_type, data)
        if isinstance(data, (str, bytes)):
            # TODO mypy #1533
            payload = ujson.loads(data)  # type: ignore
            asyncio.ensure_future(self._handler(payload))
        else:
            LOG.debug("Unhandle websocket message: %s", message_type)

    def connection_lost(self, error: Optional[Exception]) -> None:
        if error:
            LOG.error(error)


class AriRequest(BaseRequest):
    def __init__(self, event: Event) -> None:
        super().__init__(event.app.state)
        self._event = event

    async def data(self) -> dict:
        return self._event.data

    @property
    def initial(self) -> Event:
        return self._event

    @property
    def config(self) -> dict:
        return self._event.config

    @property
    def method(self) -> None:
        return None

    @property
    def path(self) -> str:
        return self._event.type


async def middleware(event: Event, handler: Callable[[BaseRequest], Awaitable[None]]):
    request = AriRequest(event)
    await handler(request)


class Router:
    def __init__(self) -> None:
        self._routes: dict = dict()

    def add(
        self,
        event: str,
        handler: Callable[[Union[BaseRequest, Event]], Awaitable[None]],
        config: Optional[dict] = None,
    ):
        if config is None:
            config = dict()

        self._routes[event.lower()] = (handler, config)

    def resolve(
        self, event: str
    ) -> Union[
        Tuple[None, None],
        Tuple[Callable[[Union[BaseRequest, Event]], Awaitable[None]], dict],
    ]:
        return self._routes.get(event.lower(), self._routes.get("*", (None, None)))
