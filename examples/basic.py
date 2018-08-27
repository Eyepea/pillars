import functools
import logging

import aiohttp.web
import pillars

LOG = logging.getLogger()


def main():
    app = pillars.Application(name="example")
    register_transports(app)
    app.run()


async def hello_world(request):
    LOG.debug(request)
    return pillars.Response(status=200, data={"data": "Hello world"})


def register_transports(app):

    http = pillars.transports.http.Application()
    app.listen(
        app=http,
        name="http",
        runner=aiohttp.web.AppRunner(http),
        sites=(functools.partial(aiohttp.web.TCPSite, host="127.0.01", port=8080),),
    )

    http.router.add_route("GET", "/", hello_world)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
