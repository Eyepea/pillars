import collections
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

LOG = logging.getLogger(__name__)


class BaseRequest:
    def __init__(self, app_state: collections.ChainMap) -> None:
        self.id = uuid.uuid4()
        self._state = app_state.new_child()

    # MutableMapping API
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

    async def data(self) -> dict:
        raise NotImplementedError()

    @property
    def initial(self) -> Any:
        raise NotImplementedError()

    @property
    def config(self) -> dict:
        raise NotImplementedError()

    @property
    def method(self) -> Optional[str]:
        raise NotImplementedError()

    @property
    def path(self) -> str:
        raise NotImplementedError()


@dataclass
class Response:
    status: int
    data: dict = field(default_factory=dict)
