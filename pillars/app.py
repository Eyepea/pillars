import asyncio
import collections
import logging
import signal
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from aiohttp import signals
from aiohttp.web_runner import BaseRunner, BaseSite
import setproctitle

from . import exceptions

LOG = logging.getLogger(__name__)


@dataclass
class SubApp:
    name: str
    app: Any
    sites: List[Callable[[BaseRunner], BaseSite]]
    runner: BaseRunner

    async def status(self) -> bool:
        result = list()
        if hasattr(self.app, "status"):
            result.append(await self.app.status())

        for site in self.sites:
            if hasattr(site, "status"):
                result.append(await site.status())  # type: ignore

        return all(result)


class Application(collections.MutableMapping):
    def __init__(
        self, name: str, state: Optional[collections.MutableMapping] = None
    ) -> None:

        if name:
            setproctitle.setproctitle(name)

        self._state = state or dict()
        self._frozen = False
        self._subapps: dict = dict()
        self._on_startup: signals.Signal = signals.Signal(self)
        self._on_cleanup: signals.Signal = signals.Signal(self)
        self._on_shutdown: signals.Signal = signals.Signal(self)
        self["name"] = name

    @property
    def name(self) -> str:
        return self["name"]

    @property
    def subapps(self) -> dict:
        return self._subapps

    # Start Application
    def run(self) -> None:
        LOG.debug("Starting Application")
        loop = asyncio.get_event_loop()

        try:
            loop.add_signal_handler(signal.SIGINT, self._raise_exit)
            loop.add_signal_handler(signal.SIGTERM, self._raise_exit)
        except NotImplementedError:
            LOG.debug("Loop signal not supported")

        loop.run_until_complete(self.start())
        try:
            loop.run_forever()
        except (KeyboardInterrupt, exceptions.GracefulExit):
            pass
        except Exception:
            raise
        finally:
            loop.run_until_complete(self.stop())

    def listen(
        self,
        *,
        app: Any,
        sites: List[Callable[[BaseRunner], BaseSite]],
        runner: BaseRunner,
        name: Optional[str] = None,
    ):
        if not name:
            name = f"{app.__module__}.{app.__class__.__qualname__}"

        subapp = SubApp(name=name, app=app, sites=sites, runner=runner)
        if self._frozen:
            raise RuntimeError("Cannot add subapp to frozen application")
        elif not isinstance(subapp, SubApp):
            raise TypeError(f"SubApp {subapp} is not of type {type(SubApp)}")

        self._subapps[subapp.name] = subapp

    def _freeze(self) -> None:
        if self._frozen:
            return

        self.on_startup.freeze()
        self.on_shutdown.freeze()
        self.on_cleanup.freeze()
        self._frozen = True

    async def start(self) -> None:
        self._freeze()
        await self.on_startup.send(self)
        await asyncio.gather(
            *(subapp.runner.setup() for subapp in self._subapps.values())
        )
        for subapp in self._subapps.values():
            subapp.sites = [site(subapp.runner) for site in subapp.sites]
            subapp.app._container = self

            if isinstance(subapp.app, collections.MutableMapping):
                subapp.app.state = collections.ChainMap(  # type: ignore
                    subapp.app, self._state
                )
            else:
                subapp.app.state = collections.ChainMap({}, self._state)

        await asyncio.gather(
            *(
                site.start()
                for subapp in self._subapps.values()
                for site in subapp.sites
            )
        )

    async def stop(self) -> None:
        LOG.debug("Stopping application")
        coros = (subapp.runner.shutdown() for subapp in self._subapps.values())
        await asyncio.gather(*coros)
        await self.on_shutdown.send(self)
        coros = (subapp.runner.cleanup() for subapp in self._subapps.values())
        await asyncio.gather(*coros)
        await self.on_cleanup.send(self)

    async def status(self) -> dict:
        result = dict()
        for subapp in self._subapps.values():
            if hasattr(subapp, "status"):
                result[subapp.name] = await subapp.status()

        return result

    ###########
    # Signals #
    ###########
    @property
    def on_startup(self) -> signals.Signal:
        return self._on_startup

    @property
    def on_shutdown(self) -> signals.Signal:
        return self._on_shutdown

    @property
    def on_cleanup(self) -> signals.Signal:
        return self._on_cleanup

    def _raise_exit(self) -> None:
        raise exceptions.GracefulExit()

    ######################
    # MutableMapping API #
    ######################
    def __eq__(self, other):
        return self is other

    def __getitem__(self, key):
        return self._state[key]

    def __setitem__(self, key, value):
        self._state[key] = value

    def __delitem__(self, key):
        del self._state[key]

    def __len__(self):
        return len(self._state)

    def __iter__(self):
        return iter(self._state)
