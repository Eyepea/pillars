import contextlib
from typing import Any, Awaitable, Callable

from ..request import BaseRequest


async def pg(request: BaseRequest, handler: Callable[[BaseRequest], Awaitable[Any]]):
    async with contextlib.AsyncExitStack() as stack:
        if "pg" in request.config:
            request["pg_connection"] = await stack.enter_async_context(
                request["pg"].connection()
            )
        elif "pg_transaction" in request.config:
            request["pg_connection"] = await stack.enter_async_context(
                request["pg"].connection()
            )
            await stack.enter_async_context(request["pg_connection"].transaction())

    return await handler(request)
