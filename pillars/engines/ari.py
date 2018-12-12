import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
import ujson

from ..app import Application

LOG = logging.getLogger(__name__)


@dataclass
class ChannelCounter:
    time: int = field(default_factory=lambda: int(time.time()))
    counter: int = field(default=0)

    def new(self):
        current_time = int(time.time())
        if current_time == self.time:
            self.counter += 1
        else:
            self.time = current_time
            self.counter = 1

        return f"{current_time}.{self.counter}"


class AriClient:
    def __init__(self, app: Application, url: str, auth: aiohttp.BasicAuth) -> None:

        self._name = app["name"]
        self._base_url = url
        self._auth = auth
        self._channel_counter = ChannelCounter()
        self._client: Optional[aiohttp.ClientSession] = None

        app.on_startup.append(self._startup)
        app.on_cleanup.append(self._cleanup)

    async def _startup(self, app: Application) -> None:
        LOG.debug("Starting ARI client engine")
        self._client = aiohttp.ClientSession(
            auth=self._auth, json_serialize=ujson.dumps
        )

    async def _cleanup(self, app: Application) -> None:
        LOG.debug("Cleaning up ARI client engine")
        if self._client:
            await self._client.close()

    async def status(self) -> bool:
        try:
            await self.request("GET", f"applications/{self._name}")
        except Exception:
            LOG.exception("ARI Client failed status")
            return False
        else:
            return True

    async def request(
        self,
        method: str,
        url: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        LOG.log(4, "ARI request %s to %s with %s %s", method, url, params, data)
        url = self._base_url + url
        response = await self._request(method, url, data, params)
        return response

    async def _request(
        self,
        method: str,
        url: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:

        if not self._client:
            raise RuntimeError("Engine not started")

        response = await self._client.request(method, url, json=data, params=params)
        response.raise_for_status()
        response_data = await response.text()
        if response_data:
            return ujson.loads(response_data)
        else:
            return {}

    ###########
    # HELPERS #
    ###########

    def generate_channel_id(self, channel_prefix: str = None) -> str:
        if channel_prefix:
            return f"{channel_prefix}.{self._channel_counter.new()}"
        else:
            return self._channel_counter.new()
