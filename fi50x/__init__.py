"""
fi50x — a transport-agnostic driver library for the FI-50X UHF RFID reader.

Public API:
    from fi50x import RFIDReader, SerialTransport, Bank, Regulation

The driver knows only the FI-50X ASCII protocol; wire it to any transport
(RabbitMQ service, REST API, CLI) on top.
"""

from .version import __version__
from .driver import RFIDReader
from .transport import Transport, SerialTransport
from .protocol import Bank, Regulation, BAUDRATE_CODES
from .responses import (
    Tag,
    ReadResult,
    WriteResult,
    BankReadWithEpc,
    InventoryResult,
)
from .tracking import TagTracker, TrackerDelta
from .exceptions import (
    ReaderError,
    NoResponseError,
    InvalidCommandError,
    ProtocolError,
    NoTagError,
    TagError,
    OtherError,
    MemoryOverrunError,
    MemoryLockedError,
    InsufficientPowerError,
    NonSpecificError,
)
from . import crc

__all__ = [
    "RFIDReader",
    "Transport",
    "SerialTransport",
    "Bank",
    "Regulation",
    "BAUDRATE_CODES",
    "Tag",
    "ReadResult",
    "WriteResult",
    "BankReadWithEpc",
    "InventoryResult",
    "TagTracker",
    "TrackerDelta",
    "ReaderError",
    "NoResponseError",
    "InvalidCommandError",
    "ProtocolError",
    "NoTagError",
    "TagError",
    "OtherError",
    "MemoryOverrunError",
    "MemoryLockedError",
    "InsufficientPowerError",
    "NonSpecificError",
    "crc",
    "__version__",
]
