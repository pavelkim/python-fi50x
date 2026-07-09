"""
Typed result objects returned by the driver.

Keeping these separate from the driver keeps the wire-parsing logic testable and
gives consumers (RabbitMQ service, a future REST API, tests) a stable shape to
serialise.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

from . import crc as _crc


@dataclass
class Tag:
    """
    A single tag observed via Q / U inventory.

    The reader returns ``PC + EPC + CRC16`` as one hex string; the fields below
    split it out. ``crc_valid`` is ``None`` when verification was not attempted.
    """

    pc: str
    epc: str
    crc: str
    raw: str
    crc_valid: Optional[bool] = None

    @classmethod
    def from_epc_response(cls, payload: str, *, verify: bool = True) -> "Tag":
        """
        Parse a ``PC(4) + EPC(n) + CRC(4)`` hex payload into a :class:`Tag`.

        Args:
            payload: the hex string following the ``Q``/``U`` command character.
            verify: when True, compute and record the CRC-16 check.
        """
        if len(payload) < 8:
            raise ValueError(f"EPC payload too short: {payload!r}")
        pc = payload[:4]
        epc = payload[4:-4]
        crc = payload[-4:]
        crc_valid = _crc.verify_epc(pc, epc, crc) if verify else None
        return cls(pc=pc, epc=epc, crc=crc, raw=payload, crc_valid=crc_valid)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReadResult:
    """Result of an ``R`` read: the raw hex data plus the request parameters."""

    bank: int
    address: int
    length: int
    data: str  # hex string, length == length * 4

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WriteResult:
    """
    Result of a ``W`` write.

    ``ok`` is True when the reader replied ``<OK>``. Some firmware instead reports
    the number of words written (``Z00``..``Z1F``); ``words_written`` carries that.
    """

    ok: bool
    bank: int
    address: int
    length: int
    words_written: Optional[int] = None
    raw: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BankReadWithEpc:
    """Result of a UR/QR "read bank data with EPC" operation for one tag."""

    tag: Tag
    data: str  # hex string of the read bank data

    def to_dict(self) -> Dict[str, Any]:
        return {"tag": self.tag.to_dict(), "data": self.data}


@dataclass
class InventoryResult:
    """Result of a multi-tag ``U`` inventory sweep."""

    tags: List[Tag] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"tags": [t.to_dict() for t in self.tags]}
