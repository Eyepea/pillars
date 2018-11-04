import functools
import logging

import dbussy
import pillars

LOG = logging.getLogger()


def main():
    app = pillars.Application(name="example")
    register_transports(app)
    app.run()


async def display(signal):
    print(f"Global shortcut pressed: {signal.arguments[1]}")


def register_transports(app):

    dbus = pillars.transports.dbus.Application(app)

    # Register Handler
    dbus.router.add(
        handler=display,
        interface="org.kde.kglobalaccel.Component",
        member="globalShortcutPressed",
    )

    app.listen(
        app=dbus,
        name="dbus",
        runner=pillars.transports.dbus.AppRunner(dbus),
        sites=(
            functools.partial(
                pillars.sites.dbus.DbusSignalListener, bus=dbussy.DBUS.BUS_SESSION
            ),
            functools.partial(
                pillars.sites.dbus.DbusSignalListener, bus=dbussy.DBUS.BUS_SYSTEM
            ),
        ),
    )

    # # Ask DBUS to only receive events from specific interface
    # match = pillars.sites.dbus.DbusMatch(
    #     interface="org.kde.kglobalaccel.Component"
    # )

    # app.listen(
    #     app=dbus,
    #     name="dbus",
    #     runner=pillars.transports.dbus.AppRunner(dbus),
    #     sites=(
    #         functools.partial(
    #             pillars.sites.dbus.DbusSignalListener, bus=dbussy.DBUS.BUS_SESSION, matches=[match, ]
    #         ),
    #     ),
    # )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
