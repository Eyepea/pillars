import asyncio
import logging
from typing import Union

import aiosip
from aiohttp.web_runner import BaseRunner

from ..sites import ProtocolType

LOG = logging.getLogger(__name__)


class Application(aiosip.Application):
    async def shutdown(self) -> None:
        await self.close()

    async def cleanup(self) -> None:
        pass


class AppRunner(BaseRunner):
    def __init__(self, app: Application) -> None:
        super().__init__()
        self._app = app

    async def shutdown(self) -> None:
        await self._app.shutdown()

    async def _make_server(self) -> "SipServer":
        return SipServer(app=self._app)

    async def _cleanup_server(self) -> None:
        await self._app.cleanup()

    def _reg_site(self, site) -> None:
        super()._reg_site(site)

        if self._server._protocol_type is None:
            self._server._protocol_type = site._protocol_type
        elif self._server._protocol_type != site._protocol_type:
            raise TypeError("All sites must use the same protocol_type")


class SipServer:
    def __init__(self, app: Application) -> None:
        self._app = app
        self._protocol_type = None

    def __call__(self) -> Union[aiosip.WS, aiosip.TCP, aiosip.UDP]:

        if self._protocol_type == ProtocolType.STREAM:
            protocol = aiosip.TCP
        elif self._protocol_type == ProtocolType.DATAGRAM:
            protocol = aiosip.UDP
        else:
            raise RuntimeError("Unknown protocol type")

        return protocol(self._app, loop=asyncio.get_event_loop())

    async def shutdown(self, timeout: int) -> None:
        pass
