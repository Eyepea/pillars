import json
import logging
import uuid


class LoggingSTDOutFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.WARNING


class JSONUUIDEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, uuid.UUID):
            return o.hex
        return super().default(self, o)
