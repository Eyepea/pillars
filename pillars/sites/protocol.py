import enum
import logging

from aiohttp.web_runner import SockSite, TCPSite, UnixSite

LOG = logging.getLogger(__name__)


@enum.unique
class ProtocolType(enum.Enum):
    STREAM = 1
    DATAGRAM = 2
    WS = 3


TCPSite._protocol_type = ProtocolType.STREAM  # type: ignore
UnixSite._protocol_type = ProtocolType.STREAM  # type: ignore
SockSite._protocol_type = ProtocolType.STREAM  # type: ignore
