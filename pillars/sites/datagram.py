import asyncio
import logging
import os
import socket
import stat
from typing import Optional

from aiohttp.web_runner import (  # noQa: F401
    BaseRunner,
    BaseSite,
    SockSite,
    TCPSite,
    UnixSite,
)

from .protocol import ProtocolType

LOG = logging.getLogger(__name__)


class DatagramServer:
    """
    Shim to present a unified server interface.
    """

    def __init__(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def close(self) -> None:
        self.transport.close()

    async def wait_closed(self) -> None:
        pass


class UDPSite(BaseSite):
    def __init__(
        self,
        runner: BaseRunner,
        host: str = None,
        port: int = None,
        *,
        shutdown_timeout: float = 60.0,
        reuse_address: Optional[bool] = None,
        reuse_port=Optional[bool],
    ) -> None:
        super().__init__(runner, shutdown_timeout=shutdown_timeout)

        if host is None:
            host = "0.0.0.0"
        self._host = host
        if port is None:
            port = 8443 if self._ssl_context else 8080
        self._port = port
        self._reuse_address = reuse_address
        self._reuse_port = reuse_port
        self._protocol_type = ProtocolType.DATAGRAM

    @property
    def name(self) -> str:
        return f"UDP://{self._host}:{self._port}"

    async def start(self) -> None:
        await super().start()
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            self._runner.server,
            local_addr=(self._host, self._port),
            reuse_address=self._reuse_address,
            reuse_port=self._reuse_port,
        )  # type: ignore
        self._server = DatagramServer(transport)  # type: ignore


class DatagramUnixSite(BaseSite):
    def __init__(
        self, runner: BaseRunner, path: str, *, shutdown_timeout: float = 60.0
    ) -> None:
        super().__init__(runner, shutdown_timeout=shutdown_timeout)
        self._path = path
        self._protocol_type = ProtocolType.DATAGRAM

    @property
    def name(self) -> str:
        return f"UDP://unix:{self._path}"

    async def start(self) -> None:
        await super().start()
        await self._clean_stale_unix_socket(self._path)

        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(  # type: ignore
            self._runner.server, family=socket.AF_UNIX, local_addr=self._path
        )
        self._server = DatagramServer(transport)  # type: ignore

    @staticmethod
    async def _clean_stale_unix_socket(path: str) -> None:
        if path[0] not in (0, "\x00"):
            try:
                if stat.S_ISSOCK(os.stat(path).st_mode):
                    os.remove(path)
            except FileNotFoundError:
                pass
            except OSError as err:
                # Directory may have permissions only to create socket.
                LOG.error(
                    "Unable to check or remove stale UNIX socket %r: %r", path, err
                )


class DatagramSockSite(BaseSite):
    def __init__(
        self, runner: BaseRunner, sock: socket.socket, *, shutdown_timeout: float = 60.0
    ) -> None:
        super().__init__(runner, shutdown_timeout=shutdown_timeout)
        self._sock = sock

        if hasattr(socket, "AF_UNIX") and sock.family == socket.AF_UNIX:
            name = f"UDP://unix:{sock.getsockname()}"
        else:
            host, port = sock.getsockname()[:2]
            name = f"UDP://{host}:{port}"

        self._name = name
        self._protocol_type = ProtocolType.DATAGRAM

    @property
    def name(self) -> str:
        return self._name

    async def start(self) -> None:
        await super().start()
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            self._runner.server, sock=self._sock
        )  # type: ignore
        self._server = DatagramServer(transport)  # type: ignore
