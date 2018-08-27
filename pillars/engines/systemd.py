import asyncio
import logging
import os
import socket
from typing import Awaitable, Callable, Optional

from ..app import Application

LOG = logging.getLogger(__name__)


class Watchdog:
    def __init__(
        self,
        app: Application,
        path: Optional[str] = None,
        interval: Optional[int] = None,
        healthcheck: Optional[Callable[["Watchdog"], Awaitable[None]]] = None,
    ) -> None:

        if interval is None:
            usec = int(os.environ["WATCHDOG_USEC"])
            interval = int(usec / 2000000)

        self._loop = asyncio.get_event_loop()
        self._path = path or os.environ["NOTIFY_SOCKET"]
        self._running = False
        self._interval = interval
        self._protocol: Optional[asyncio.DatagramProtocol] = None
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._healthcheck = healthcheck or self.ping

        app.on_startup.append(self._startup)
        # Shutdown the watchdog first to skip healthcheck during teardown
        app.on_shutdown.insert(0, self._shutdown)
        LOG.debug("Systemd watchdog ping interval: %s seconds", self._interval)

    async def _start(self) -> None:
        self._transport, self._protocol = await self._loop.create_datagram_endpoint(  # type: ignore
            asyncio.DatagramProtocol,
            family=socket.AF_UNIX,
            remote_addr=self._path,  # type: ignore
        )

        self.send(b"READY=1\nSTATUS=STARTING")
        await asyncio.sleep(1)
        while self._running:
            try:
                await self._healthcheck(self)
            except Exception:
                LOG.exception("Unhandle Error during healthcheck")
            await asyncio.sleep(self._interval)

    async def _startup(self, app: Application) -> None:
        LOG.debug("Starting Systemd engine")
        self._running = True
        self._task = self._loop.create_task(self._start())

    async def _shutdown(self, app: Application) -> None:
        LOG.debug("Shutting down Systemd engine")
        self._running = False
        if self._transport:
            self.send(b"STOPPING=1")
            self._transport.close()
            self._transport = None
            self._protocol = None

    def send(self, data: bytes) -> None:
        if self._transport:
            self._transport.sendto(data)
        else:
            raise RuntimeError("No transport")

    async def ping(self, _) -> None:
        LOG.debug("Sending watchdog ping")
        self.send(b"WATCHDOG=1")
