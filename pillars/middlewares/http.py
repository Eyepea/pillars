import logging
from typing import Awaitable, Callable

import aiohttp.web

from .. import exceptions
from ..request import BaseRequest

LOG = logging.getLogger(__name__)


@aiohttp.web.middleware
async def exception_handler(
    request: BaseRequest,
    handler: Callable[[BaseRequest], Awaitable[aiohttp.web.Response]],
) -> aiohttp.web.Response:

    try:
        response = await handler(request)
    except exceptions.DataValidationError as e:
        return aiohttp.web.json_response(status=400, data={"errors": e.errors})
    except exceptions.NotFound as e:
        return aiohttp.web.json_response(status=404, data={"item": e.item})
    except Exception:
        LOG.exception("Error handling request: %s", request.path)
        return aiohttp.web.json_response(status=500, data={"errors": ["Unknown error"]})
    else:
        return response
