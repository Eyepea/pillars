import asyncio
import logging
from typing import Optional, Union

import aiohttp
import aiohttp.http_websocket
from aiohttp.web_runner import (  # noQa: F401
    BaseRunner,
    BaseSite,
    SockSite,
    TCPSite,
    UnixSite,
)

from .protocol import ProtocolType

LOG = logging.getLogger(__name__)


class WSTransport(asyncio.BaseTransport):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._ws = None
        self._closing = False
        self._closed: Optional[asyncio.Task] = None

    def close(self) -> None:
        self._closing = True
        if self._ws:
            self._closed = asyncio.create_task(self._close())

    async def _close(self):
        await self._ws.close()
        self._ws = None

    async def closed(self):
        if self._closed:
            await self._closed

    async def status(self) -> bool:
        if self._ws:
            try:
                await self._ws.ping()
            except Exception:
                LOG.exception("Failed status for WS transport: %s", self._ws)
                return False
            return True
        else:
            return False

    def is_closing(self):
        """Return True if the transport is closing or closed."""
        return self._closing

    def set_protocol(self, protocol):
        """Set a new protocol."""
        raise NotImplementedError

    def get_protocol(self):
        """Return the current protocol."""
        raise NotImplementedError


class WSServer:
    """
    Shim to present a unified server interface.
    """

    def __init__(self, transport: WSTransport) -> None:
        self.transport = transport

    def close(self) -> None:
        self.transport.close()

    async def wait_closed(self) -> None:
        await self.transport.closed()


class WSProtocol(asyncio.BaseProtocol):
    def message_received(
        self,
        message_type: aiohttp.http_websocket.WSMsgType,
        data: Union[str, bytes, aiohttp.http_websocket.WSCloseCode],
        extra: str,
    ):
        raise NotImplementedError()


class WSClientSite(BaseSite):
    def __init__(
        self,
        runner: BaseRunner,
        url: str,
        *,
        shutdown_timeout: float = 60.0,
        session: aiohttp.ClientSession = None,
    ) -> None:
        super().__init__(runner, shutdown_timeout=shutdown_timeout)
        self._url = url
        self._name = f"WS://{url}"
        self._server = None
        self._session = session or aiohttp.ClientSession()
        self._protocol: Optional[WSProtocol] = None
        self._transport: Optional[WSTransport] = None
        self._closing = False
        self._protocol_type = ProtocolType.WS

    @property
    def name(self) -> str:
        return self._name

    async def start(self) -> None:
        await super().start()
        self._protocol: asyncio.Protocol = self._runner.server()
        self._transport: WSTransport = WSTransport()
        asyncio.create_task(self._ws_connection())  # type: ignore
        self._server = WSServer(transport=self._transport)

    async def stop(self) -> None:
        self._closing = True
        await super().stop()

    async def _ws_connection(self) -> None:
        if not self._transport or not self._protocol:
            raise TypeError("Missing transport and protocol")

        try:
            async with self._session.ws_connect(self._url) as ws:
                self._transport._ws = ws
                self._protocol.connection_made(self._transport)
                async for message in ws:
                    LOG.log(2, "Data received: %s", message)
                    self._protocol.message_received(
                        message.type, message.data, message.extra
                    )
                    # WSMsgType.CLOSE should call connection_lost

            # TODO: mypy #5537 09/2018
            self._protocol.connection_lost(None)  # type: ignore
        except aiohttp.client_exceptions.ClientError as e:
            LOG.debug("Failed to connect to %: %s", self._url, e)
            await asyncio.sleep(0.1)
        except Exception as e:
            self._protocol.connection_lost(e)

        if self._closing:
            await self._session.close()
        else:
            asyncio.create_task(self._ws_connection())  # type: ignore

    async def status(self) -> bool:
        if self._transport:
            return await self._transport.status()
        else:
            return False
