import logging
from typing import Awaitable, Callable, Optional

import aiohttp.web
import cerberus
from aiohttp.web_urldispatcher import UrlDispatcher
import ujson

from ..exceptions import DataValidationError
from ..request import BaseRequest, Response

LOG = logging.getLogger(__name__)


@aiohttp.web.middleware
async def middleware(
    request: aiohttp.web.Request,
    handler: Callable[["HttpRequest"], Awaitable[aiohttp.web.Response]],
):
    common_request = HttpRequest(request)
    response = await handler(common_request)
    if isinstance(response, Response):
        return aiohttp.web.json_response(status=response.status, data=response.data)
    else:
        return response


class HttpRequest(BaseRequest):
    def __init__(self, request: aiohttp.web.Request) -> None:
        super().__init__(request.app.state)
        self._request = request
        self._data: Optional[dict] = None
        self["validator"] = self._request["validator"]

    async def data(self, validate: bool = None) -> dict:
        if self._data is None:
            if "json" in self["config"]:
                self._data = await self._request.json(loads=ujson.loads)
            elif self._request.method == "GET":
                self._data = dict(self._request.query)
            else:
                self._data = {"text": await self._request.text()}
                return self._data

            # TODO mypy (self._data can not be None)
            self._data.update(self._request.match_info)  # type: ignore

            if validate:
                if self["validator"].validate(self._data):
                    self._data = self["validator"].document
                else:
                    raise DataValidationError(self["validator"].errors)

        return self._data or dict()

    @property
    def initial(self) -> aiohttp.web.Request:
        return self._request

    @property
    def config(self) -> dict:
        return self._request["config"]

    @property
    def method(self) -> str:
        return self._request.method

    @property
    def path(self) -> str:
        return self._request.path


class Application(aiohttp.web.Application):
    def __init__(self, **kwargs) -> None:
        if "router" not in kwargs:
            kwargs["router"] = Router()

        if "middlewares" not in kwargs:
            kwargs["middlewares"] = (middleware,)
        else:
            kwargs["middlewares"] = list(kwargs["middlewares"])
            kwargs["middlewares"].insert(0, middleware)

        super().__init__(**kwargs)


class Router(UrlDispatcher):
    def __init__(self) -> None:
        super().__init__()
        self.config: dict = dict()
        self.validators: dict = dict()

    def add_route(
        self,
        *args,
        config: Optional[dict] = None,
        data_schema: Optional[dict] = None,
        **kwargs
    ):
        route = super().add_route(*args, **kwargs)

        if data_schema:
            self.validators[route] = cerberus.Validator(data_schema)

        if config:
            self.config[route] = set(config)
        else:
            self.config[route] = set()
        return route

    async def resolve(self, request: aiohttp.web.Request) -> aiohttp.web.Resource:
        resource = await super().resolve(request)
        request["config"] = self.config.get(resource.route, ())
        request["validator"] = self.validators.get(resource.route)
        return resource
