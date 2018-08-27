import logging

LOG = logging.getLogger(__name__)


class GracefulExit(SystemExit):
    code = 0


class DataValidationError(Exception):
    def __init__(self, errors: dict) -> None:
        self.errors = errors


class NotFound(Exception):
    def __init__(self, item: dict) -> None:
        self.item = item
