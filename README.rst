`Pillars <http://pypillars.readthedocs.io>`_
============================================

Collection of helpers for building asyncio daemons.

.. image:: https://readthedocs.org/projects/pypillars/badge/?version=latest
    :target: http://pypillars.readthedocs.io/en/latest/
    :alt: Documentation Status
.. image:: https://travis-ci.org/Eyepea/pillars.svg?branch=master
    :target: https://travis-ci.org/Eyepea/pillars
    :alt: Travis-ci status
.. image:: https://badge.fury.io/py/pillars.svg
    :target: https://pypi.org/project/pillars/
    :alt: PyPI status

Installation
------------

Pillars is `available on PyPI <https://pypi.org/project/pillars/>`_.

.. code::

    $ pip3 install pillars

Quickstart
----------

.. code-block:: python

    import pillars
    import aiohttp

    app = pillars.Application(name="example")
    http = pillars.transports.http.Application()

    app.listen(
        app=http,
        name="http",
        runner=aiohttp.web.AppRunner(http),
        sites=(functools.partial(aiohttp.web.TCPSite, host="127.0.01", port=8080),),
    )

    http.router.add_route("GET", "/", hello_world)

    async def hello_world(request):
        return pillars.Response(status=200, data={"data": "Hello world"})

For more examples see the `examples folder <https://github.com/eyepea/pillars/tree/master/examples>`_.

Changelog
---------

0.2.3
`````

* Add custom json encoder for UUID
* Add `json_encoder` argument to `pillars.Response`

0.2.2
`````

* Fix ARI engine shutdown

0.2.1
`````

* Properly close websocket connection
* Remove pg uuid encoder
* Log when pg jsonb encode fails
* Use aiohttp exception for ARI transports

0.1.1
`````

* Initial release
