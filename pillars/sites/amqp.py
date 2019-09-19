import asyncio
import logging
from typing import Awaitable, Callable, Optional, Union

import aiohttp
import aiohttp.http_websocket
import aio_pika
import json

from ..base import BaseRunner, BaseSite
from .protocol import ProtocolType

LOG = logging.getLogger(__name__)


class AmqpTransport(asyncio.BaseTransport):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
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


class AmqpProtocol(asyncio.BaseProtocol):
    def message_received(
        self,
        message_type: str,
        data: dict,
        extra: str,
    ):
        raise NotImplementedError()


class AmqpServer:
    def __init__(self, transport: AmqpTransport) -> None:
        self.transport = transport

    def close(self) -> None:
        self.transport.close()

    async def wait_closed(self) -> None:
        await self.transport.closed()


class AmqpClient(BaseSite):
    def __init__(
        self,
        runner: BaseRunner,
        *,
        shutdown_timeout: float = 60.0,
        session: aiohttp.ClientSession = None,
        on_connection: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        super().__init__(runner, shutdown_timeout=shutdown_timeout)
        self._connection = None
        self._channel = None
        self._exchange = False
        self._queue = None
        self._protocol = None
        self._on_connection = on_connection
        self._loop = asyncio.get_event_loop()

    @property
    def name(self) -> str:
        return self._name

    async def start(self) -> None:
        await super().start()
        await self.create_connection()
        asyncio.create_task(self._amqp_consumer())

    async def stop(self) -> None:
        self._closing = True
        await super().stop()

    async def create_connection(self):
        LOG.debug('AAAA Create a New Queue')
        self._protocol = asyncio.Protocol = self._runner.server()
        self._connection = await aio_pika.connect("amqp://guest:guest@localhost", loop=self._loop)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            "asterisk", aio_pika.ExchangeType.TOPIC
        )
        self._queue = await self._channel.declare_queue('')
        await self._queue.bind(self._exchange, routing_key='stasis.app.potter')
        asyncio.create_task(self._connected())

    async def _amqp_consumer(self) -> None:
        try:
            while True:
                await self._queue.consume(self.callback)

        except Exception as e:
            LOG.info("ERROR : %s" % e)

    async def callback(self, message):
        with message.process():
            self._protocol.message_received(data=json.loads(message.body.decode()), extra='', message_type='json')

    async def _connected(self) -> None:
        try:
            if self._on_connection:
                await self._on_connection()
        except Exception:
            LOG.exception(f"Error calling 'on_connection' for: {self}")

