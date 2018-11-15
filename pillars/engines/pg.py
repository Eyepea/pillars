import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

import async_timeout
import asyncpg
import ujson

from ..app import Application

LOG = logging.getLogger(__name__)


class PG:
    def __init__(
        self,
        app: Application,
        *args,
        reconnection_timeoff: int = 10,
        shutdown_timeout: int = 5,
        **kwargs
    ) -> None:
        self._loop = asyncio.get_event_loop()
        self._task: Optional[asyncio.Task] = None
        self._result: asyncio.Future = asyncio.Future()
        self._connection_info = (args, kwargs)
        self._shutdown_timeout = shutdown_timeout
        self._reconnection_timeoff = reconnection_timeoff

        app.on_startup.append(self._startup)
        app.on_shutdown.append(self._shutdown)
        app.on_cleanup.append(self._cleanup)

    async def _connect(self) -> None:
        try:
            pool = await asyncpg.create_pool(
                *self._connection_info[0], **self._connection_info[1]
            )
        except ConnectionError:
            LOG.exception("PostgreSQL connection error")
            await asyncio.sleep(self._reconnection_timeoff)
            self._task = self._loop.create_task(self._connect())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            LOG.exception("PostgreSQL connection error")
            self._result.set_exception(e)
        else:
            LOG.info("PostgreSQL connection pool created")
            self._result.set_result(pool)

    @asynccontextmanager
    async def connection(self, timeout: int = 5) -> asyncpg.Connection:
        async with async_timeout.timeout(timeout):
            pool = await asyncio.shield(self._result)
            try:
                connection = await pool.acquire()
            except ConnectionError:
                LOG.debug("Connection error while acquiring connection")
                self._result = asyncio.Future()
                self._task = self._loop.create_task(self._connect())
                pool = await asyncio.shield(self._result)
                connection = await pool.acquire()
            try:
                yield connection
            finally:
                await pool.release(connection)

    async def status(self, timeout: int = 2) -> bool:
        try:
            async with self.connection(timeout=timeout) as con:
                await con.fetchval("SELECT 1")
        except asyncio.TimeoutError:
            return False
        except Exception:
            LOG.exception("PostgreSQL failed status")
            return False
        else:
            LOG.log(4, "PostgreSQL status OK")
            return True

    async def _startup(self, app: Application) -> None:
        LOG.debug("Starting PostgreSQL engine")
        self._task = self._loop.create_task(self._connect())

    async def _shutdown(self, app: Application) -> None:
        LOG.debug("Shutting down PostgreSQL engine")
        if self._task and not self._task.done():
            self._task.cancel()

        if not self._result.done():
            self._result.cancel()

    async def _cleanup(self, app: Application) -> None:
        LOG.debug("Cleaning up PostgreSQL engine")
        try:
            pool = await self._result
        except asyncio.CancelledError:
            pass
        else:
            await asyncio.wait_for(pool.close(), timeout=self._shutdown_timeout)


async def register_json_codec(con: asyncpg.Connection) -> None:
    await con.set_type_codec(
        "json", encoder=ujson.dumps, decoder=ujson.loads, schema="pg_catalog"
    )

    await con.set_type_codec(
        "jsonb",
        encoder=jsonb_encoder,
        decoder=jsonb_decoder,
        schema="pg_catalog",
        format="binary",
    )


def jsonb_encoder(value: str) -> bytes:
    try:
        return b"\x01" + ujson.dumps(value).encode("utf-8")
    except Exception:
        LOG.error("""Unable to encode to JSONB: %s""", value)
        raise


def jsonb_decoder(value: bytes) -> dict:
    return ujson.loads(value[1:].decode("utf-8"))
