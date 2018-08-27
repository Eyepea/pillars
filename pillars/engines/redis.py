import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

import aioredis
import async_timeout

from ..app import Application

LOG = logging.getLogger(__name__)


class Redis:
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
            pool = await aioredis.create_pool(
                *self._connection_info[0], **self._connection_info[1]
            )
        except ConnectionError:
            LOG.exception("Redis connection error")
            await asyncio.sleep(self._reconnection_timeoff)
            self._task = self._loop.create_task(self._connect())
        except Exception as e:
            LOG.exception("Redis connection error")
            self._result.set_exception(e)
        else:
            LOG.info("Redis connection pool created")
            self._result.set_result(pool)

    @asynccontextmanager
    async def connection(self, timeout: int = 5) -> aioredis.RedisConnection:
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
                pool.release(connection)

    async def status(self, timeout: int = 2) -> bool:
        try:
            async with self.connection(timeout=timeout) as con:
                await con.execute("SET", "xxx_STATUS", 1)
                await con.execute("DEL", "xxx_STATUS", 1)
        except asyncio.TimeoutError:
            return False
        except Exception:
            LOG.exception("Redis failed status")
            return False
        else:
            LOG.log(4, "Redis status OK")
            return True

    async def _startup(self, app: Application) -> None:
        LOG.debug("Starting Redis engine")
        self._task = self._loop.create_task(self._connect())
        self._result = asyncio.Future()

    async def _shutdown(self, app: Application) -> None:
        LOG.debug("Shutting down Redis engine")
        if self._task and not self._task.done():
            self._task.cancel()

        if self._result.done():
            pool = await self._result
            pool.close()
        else:
            self._result.cancel()

    async def _cleanup(self, app: Application) -> None:
        LOG.debug("Cleaning up Redis engine")
        try:
            pool = await self._result
        except asyncio.CancelledError:
            pass
        else:
            await asyncio.wait_for(pool.wait_closed(), timeout=self._shutdown_timeout)
