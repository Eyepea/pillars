import functools
import logging
import os

import aiohttp.web
import pillars

LOG = logging.getLogger()

ARI_USER = os.getenv("ARI_USER")
ARI_PASSWORD = os.getenv("ARI_PASSWORD")

PG_DB = os.getenv("PG_DB")
PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")


def main():
    app = pillars.Application(name="example")
    register_transports(app)
    register_engines(app)
    app.run()


async def no_config(request):
    LOG.debug(request)

    async with request["pg"].connection() as con:
        await con.execute("SELECT 1")

    return aiohttp.web.Response(status=200, text="no config")


async def with_config(request):
    LOG.debug(request)

    await request["pg_connection"].execute("SELECT 1")
    return aiohttp.web.Response(status=200, text="with config")


async def ari_event_log(request):
    data = await request.data()
    LOG.debug(data)


def register_transports(app):
    http = pillars.transports.http.Application(middlewares=(pillars.middlewares.pg,))
    app.listen(
        app=http,
        name="http",
        runner=aiohttp.web.AppRunner(http),
        sites=(functools.partial(aiohttp.web.TCPSite, host="127.0.0.1", port=8080),),
    )

    http.router.add_route("GET", "/no_config", no_config)
    http.router.add_route("GET", "/with_config", with_config, config=["pg"])

    ari = pillars.transports.ari.Application(
        app=app, middlewares=(pillars.middlewares.pg,)
    )
    app.listen(
        app=ari,
        name="ari",
        runner=pillars.transports.ari.AppRunner(ari),
        sites=(
            functools.partial(
                pillars.sites.WSClientSite,
                url=f"ws://localhost:8088/ari/events?api_key={ARI_USER}:{ARI_PASSWORD}&app={app['name']}&subscribeAll=True",
            )
        ),
    )

    ari.router.add_route("*", ari_event_log)


def register_engines(app):

    app["pg"] = pillars.engines.pg.PG(
        app=app,
        host="127.0.0.1",
        port=5432,
        user=PG_USER,
        database=PG_DB,
        password=PG_PASSWORD,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
