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
    print(f"RECEIVED: {signal}")


def register_transports(app):

    dbus = pillars.transports.dbus.Application(app)

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
                pillars.sites.dbus.DbusSignalListener, bus=dbussy.DBUS.BUS_SESSION
            ),
        ),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    # To see all incoming signal set logging level to 4
    # logging.basicConfig(level=4)

    main()
