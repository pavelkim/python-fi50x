"""
RFIDReader — a transport-agnostic driver for the FI-50X UHF RFID reader.

This is the reusable base library: it knows the FI-50X ASCII protocol and nothing
about how it is exposed (RabbitMQ, REST, CLI, …). It talks to a
:class:`~fi50x.transport.Transport`, so it can be exercised against real hardware
or a scripted fake in tests.

Scope of this module: inventory + read/write plus the tag-management commands
needed to manage inventory tags (access password, kill, lock, select), power and
regulation. GPIO, frequency tuning, baud switching, command logging and the AA
binary protocol are intentionally not implemented yet.
"""

import logging
import time
from typing import Iterator, List, Optional

from . import protocol
from .protocol import Bank, Regulation
from .transport import Transport, SerialTransport
from .responses import (
    Tag,
    ReadResult,
    WriteResult,
    BankReadWithEpc,
    InventoryResult,
)
from .exceptions import (
    NoResponseError,
    InvalidCommandError,
    ProtocolError,
    NoTagError,
    error_for,
    ERROR_CODES,
)

logger = logging.getLogger(__name__)


class RFIDReader:
    """
    High-level interface to a single FI-50X reader.

    All methods that touch the port do so inside ``transport.lock`` so that a whole
    command/response exchange is atomic even when multiple threads share the reader
    (e.g. a scan loop plus a command consumer).
    """

    def __init__(self, transport: Transport, *, verify_crc: bool = True) -> None:
        self.transport = transport
        self.verify_crc = verify_crc
        # Populated by refresh_reader_id(); always defined so callers/consumers can
        # reference it without guarding for AttributeError.
        self.reader_id: Optional[str] = None

    @classmethod
    def open(
        cls,
        port: str,
        *,
        baudrate: int = protocol.DEFAULT_BAUDRATE,
        timeout: float = 0.5,
        verify_crc: bool = True,
    ) -> "RFIDReader":
        """
        Convenience constructor: open a serial port and wrap it in a reader.

        Equivalent to ``RFIDReader(SerialTransport(port, ...))``. For tests or
        alternative links, construct with an explicit :class:`Transport` instead.
        """
        transport = SerialTransport(port, baudrate=baudrate, timeout=timeout)
        return cls(transport, verify_crc=verify_crc)

    # ------------------------------------------------------------------ #
    # Low-level transaction plumbing
    # ------------------------------------------------------------------ #

    def _read_frame(self) -> str:
        """
        Read one non-empty return message.

        Return messages are framed ``<LF> ... <CR><LF>``; the leading ``<LF>``
        arrives as an empty line, which we skip. Returns ``""`` on timeout.
        """
        while True:
            raw = self.transport.read_line()
            if not raw:
                return ""  # timeout
            text = raw.decode("ascii", errors="ignore").strip("\r\n")
            if text == "":
                continue
            logger.debug("<- %s (%r)", raw.hex(), text)
            return text

    def _transact(self, command: str, *, allow_empty: bool = False) -> str:
        """
        Send ``command`` and return the (prefix-stripped-by-caller) reply.

        Args:
            command: ASCII command body without framing (e.g. ``"R1,0,8"``).
            allow_empty: when True, a timeout returns ``""`` instead of raising.
                Used by "set" commands whose documented reply is ``<NULL>``.
        """
        payload = protocol.frame(command)
        with self.transport.lock:
            logger.debug("-> %s (%r)", payload.hex(), command)
            self.transport.write(payload)
            reply = self._read_frame()

        if reply == "":
            if allow_empty:
                return ""
            raise NoResponseError(f"no reply to command {command!r}")
        if reply == protocol.INVALID_COMMAND_REPLY:
            raise InvalidCommandError(f"reader rejected command {command!r}")
        return reply

    @staticmethod
    def _strip_prefix(reply: str, command_char: str) -> str:
        """Strip the leading command character the reader echoes back."""
        if reply[:1] == command_char:
            return reply[1:]
        return reply

    def _parse_tag_error(self, payload: str) -> None:
        """Raise the mapped :class:`TagError` if ``payload`` is an error code."""
        if len(payload) == 1 and payload.upper() in ERROR_CODES:
            raise error_for(payload)

    # ------------------------------------------------------------------ #
    # Identity / status
    # ------------------------------------------------------------------ #

    def firmware_version(self) -> str:
        """``V`` — reader firmware version string (``xxyy,<message>``)."""
        return self._strip_prefix(self._transact("V"), "V")

    def refresh_reader_id(self) -> Optional[str]:
        """``S`` — read the reader ID and cache it on :attr:`reader_id`."""
        reply = self._transact("S")
        self.reader_id = self._strip_prefix(reply, "S")
        logger.info("Reader ID: %s", self.reader_id)
        return self.reader_id

    # ------------------------------------------------------------------ #
    # Inventory
    # ------------------------------------------------------------------ #

    def query_epc(self) -> Optional[Tag]:
        """``Q`` — read the EPC of a single tag, or ``None`` if the field is empty."""
        payload = self._strip_prefix(self._transact("Q", allow_empty=True), "Q")
        if payload == "":
            return None
        return Tag.from_epc_response(payload, verify=self.verify_crc)

    def inventory(self, slot_q: Optional[int] = None) -> InventoryResult:
        """
        ``U`` — multi-tag EPC inventory.

        A ``U`` sweep streams one ``U<EPC>`` frame per tag and terminates with a
        bare ``U`` (or a read timeout). We drain the whole stream instead of taking
        only the first frame.

        Args:
            slot_q: optional slot-count parameter (1..0x0A) for ``U<slotQ>``.
        """
        if slot_q is not None:
            if not 0x01 <= slot_q <= 0x0A:
                raise ValueError("slot_q out of range: 1..0x0A")
            command = f"U{protocol.hexarg(slot_q)}"
        else:
            command = "U"

        result = InventoryResult()
        seen = set()
        with self.transport.lock:
            self.transport.write(protocol.frame(command))
            while True:
                frame_text = self._read_frame()
                if frame_text == "":
                    break  # timeout: end of sweep
                payload = self._strip_prefix(frame_text, "U")
                if payload == "":
                    break  # bare 'U' terminator
                try:
                    tag = Tag.from_epc_response(payload, verify=self.verify_crc)
                except ValueError:
                    logger.warning("skipping malformed U frame: %r", frame_text)
                    continue
                if tag.raw not in seen:
                    seen.add(tag.raw)
                    result.tags.append(tag)
        return result

    def stream_inventory(
        self,
        interval: float = 0.1,
        slot_q: Optional[int] = None,
    ) -> Iterator[InventoryResult]:
        """
        Yield an :class:`InventoryResult` per sweep, forever.

        Sleeps ``interval`` seconds between sweeps. Pair with
        :class:`~fi50x.tracking.TagTracker` to emit new/lost tag events. Stop by
        breaking out of the loop (e.g. on ``KeyboardInterrupt``).
        """
        while True:
            yield self.inventory(slot_q=slot_q)
            if interval:
                time.sleep(interval)

    # ------------------------------------------------------------------ #
    # Memory read / write
    # ------------------------------------------------------------------ #

    @staticmethod
    def _validate_bank_address(bank: int, address: int) -> None:
        if not 0 <= int(bank) <= 3:
            raise ValueError("bank out of range: 0..3")
        if not protocol.MIN_ADDRESS <= address <= protocol.MAX_ADDRESS:
            raise ValueError("address out of range: 0..0x3FFF")

    @staticmethod
    def _validate_length(length: int) -> None:
        if not protocol.MIN_WORD_LENGTH <= length <= protocol.MAX_WORD_LENGTH:
            raise ValueError("length out of range: 1..0x20 words")

    def read(self, bank: int, address: int, length: int) -> ReadResult:
        """
        ``R<bank>,<address>,<length>`` — read ``length`` words from tag memory.

        ``address`` and ``length`` are sent as hex on the wire (handled here).
        Raises :class:`NoTagError` if the field is empty, or a :class:`TagError`
        subclass for a reader error code.
        """
        self._validate_bank_address(bank, address)
        self._validate_length(length)
        command = f"R{protocol.hexarg(int(bank))},{protocol.hexarg(address)},{protocol.hexarg(length)}"
        payload = self._strip_prefix(self._transact(command, allow_empty=True), "R")

        if payload == "":
            raise NoTagError("no tag in RF field")
        self._parse_tag_error(payload)

        expected = length * 4
        if len(payload) != expected:
            raise ProtocolError(
                f"read returned {len(payload)} hex chars, expected {expected}: {payload!r}"
            )
        return ReadResult(bank=int(bank), address=address, length=length, data=payload)

    def write(
        self,
        bank: int,
        address: int,
        data: str,
        length: Optional[int] = None,
    ) -> WriteResult:
        """
        ``W<bank>,<address>,<length>,<data>`` — write ``data`` to tag memory.

        Args:
            bank, address: target location (address is sent as hex).
            data: hex string; its length must be a multiple of 4 (one word = 4 hex
                chars). Only a real ``0x``/``0X`` prefix is stripped — leading zero
                *digits* are significant and preserved.
            length: word count. Defaults to ``len(data) // 4`` and, if given, must
                match the data length.
        """
        self._validate_bank_address(bank, address)

        data = data.strip().upper()
        if data[:2] == "0X":
            data = data[2:]
        if len(data) == 0 or len(data) % 4 != 0:
            raise ValueError(
                f"data must be a whole number of 4-hex-char words, got {len(data)} chars"
            )
        try:
            int(data, 16)
        except ValueError:
            raise ValueError(f"data is not valid hex: {data!r}")

        words = len(data) // 4
        if length is None:
            length = words
        elif length != words:
            raise ValueError(f"length {length} does not match data ({words} words)")
        self._validate_length(length)

        command = (
            f"W{protocol.hexarg(int(bank))},{protocol.hexarg(address)},"
            f"{protocol.hexarg(length)},{data}"
        )
        payload = self._strip_prefix(self._transact(command, allow_empty=True), "W")

        if payload == "":
            raise NoTagError("no tag in RF field")
        if payload in ("<OK>", "OK"):
            return WriteResult(
                ok=True, bank=int(bank), address=address, length=length,
                words_written=length, raw=payload,
            )
        # "3Z00".."3Z1F": error code 3 (overrun) plus the words actually written.
        if payload[:2] == "3Z":
            written = int(payload[2:], 16)
            raise error_for("3", words_written=written)
        # "Z00".."Z1F": firmware reporting the word count instead of <OK>.
        if payload[:1] == "Z" and len(payload) == 3:
            written = int(payload[1:], 16)
            return WriteResult(
                ok=True, bank=int(bank), address=address, length=length,
                words_written=written, raw=payload,
            )
        self._parse_tag_error(payload)
        raise ProtocolError(f"unexpected write reply: {payload!r}")

    def read_with_epc(
        self,
        bank: int,
        address: int,
        length: int,
        slot_q: Optional[int] = None,
    ) -> List[BankReadWithEpc]:
        """
        ``UR``/``QR`` — read a bank's data together with each tag's EPC.

        With ``slot_q`` this issues the multi-tag ``U<slotQ>,R...`` form and drains
        every ``U<EPC>,R<DATA>`` frame; without it, the single-tag ``Q,R...`` form.
        """
        self._validate_bank_address(bank, address)
        self._validate_length(length)
        bank_hex = protocol.hexarg(int(bank))
        addr_hex = protocol.hexarg(address)
        len_hex = protocol.hexarg(length)

        if slot_q is not None:
            if not 0x00 <= slot_q <= 0x0A:
                raise ValueError("slot_q out of range: 0..0x0A")
            command = f"U{protocol.hexarg(slot_q)},R{bank_hex},{addr_hex},{len_hex}"
            prefix = "U"
            multi = True
        else:
            command = f"Q,R{bank_hex},{addr_hex},{len_hex}"
            prefix = "Q"
            multi = False

        results: List[BankReadWithEpc] = []
        with self.transport.lock:
            self.transport.write(protocol.frame(command))
            while True:
                frame_text = self._read_frame()
                if frame_text == "":
                    break
                results.append(self._parse_read_with_epc(frame_text, prefix, length))
                if not multi:
                    break
        return results

    def _parse_read_with_epc(self, frame_text: str, prefix: str, length: int) -> BankReadWithEpc:
        """Parse one ``{U|Q}<EPC>,R<DATA>`` frame."""
        body = self._strip_prefix(frame_text, prefix)
        self._parse_tag_error(body)
        sep = body.find(",R")
        if sep < 0:
            raise ProtocolError(f"malformed read-with-epc frame: {frame_text!r}")
        epc_payload = body[:sep]
        data = body[sep + 2:]
        tag = Tag.from_epc_response(epc_payload, verify=self.verify_crc)
        return BankReadWithEpc(tag=tag, data=data)

    # ------------------------------------------------------------------ #
    # Tag management: password, kill, lock, select
    # ------------------------------------------------------------------ #

    def set_access_password(self, password: str) -> None:
        """
        ``P<password>`` — set the access password for the *next* R/W/L command.

        One-time use: the reader consumes it on the following memory operation.
        """
        password = self._normalize_password(password)
        self._transact(f"P{password}")

    def kill(self, password: str, recom: int = 0) -> None:
        """
        ``K<password>,<recom>`` — permanently disable a tag.

        Args:
            password: 8-hex-char kill password.
            recom: recommissioning bits, 0..7.
        """
        password = self._normalize_password(password)
        if not 0 <= recom <= 7:
            raise ValueError("recom out of range: 0..7")
        payload = self._strip_prefix(
            self._transact(f"K{password},{protocol.hexarg(recom)}", allow_empty=True), "K"
        )
        self._raise_unless_ok(payload, "kill")

    def lock(self, mask: int, action: int) -> None:
        """
        ``L<mask>,<action>`` — lock/unlock memory.

        ``mask`` and ``action`` are 0..0x3FF and sent as 3 hex digits.
        See :meth:`lock_epc_write` / :meth:`unlock_epc_write` for common cases.
        """
        for name, value in (("mask", mask), ("action", action)):
            if not 0x000 <= value <= 0x3FF:
                raise ValueError(f"{name} out of range: 0..0x3FF")
        command = f"L{value_to_3hex(mask)},{value_to_3hex(action)}"
        payload = self._strip_prefix(self._transact(command, allow_empty=True), "L")
        self._raise_unless_ok(payload, "lock")

    def lock_epc_write(self) -> None:
        """Lock the EPC bank against writes (mask=0x020, action=0x020)."""
        self.lock(0x020, 0x020)

    def unlock_epc_write(self) -> None:
        """Unlock the EPC bank for writes (mask=0x020, action=0x000)."""
        self.lock(0x020, 0x000)

    def select(self, bank: int, bit_address: int, bit_length: int, bit_data: str) -> None:
        """
        ``T<bank>,<bit address>,<bit length>,<bit data>`` — select matching tags.

        Restricts subsequent operations to tags whose memory matches ``bit_data``.
        """
        self._validate_bank_address(bank, bit_address)
        if not protocol.MIN_SELECT_BITS <= bit_length <= protocol.MAX_SELECT_BITS:
            raise ValueError("bit_length out of range: 1..0x60")
        bit_data = bit_data.strip().upper()
        try:
            int(bit_data, 16)
        except ValueError:
            raise ValueError(f"bit_data is not valid hex: {bit_data!r}")
        command = (
            f"T{protocol.hexarg(int(bank))},{protocol.hexarg(bit_address)},"
            f"{protocol.hexarg(bit_length)},{bit_data}"
        )
        self._transact(command, allow_empty=True)

    # ------------------------------------------------------------------ #
    # Power / regulation
    # ------------------------------------------------------------------ #

    def get_power_register(self) -> int:
        """``N0,00`` — read the raw TX power register (0x00..0x1B)."""
        payload = self._strip_prefix(self._transact("N0,00"), "N")
        return int(payload, 16)

    def get_power_dbm(self) -> int:
        """Read the TX power as dBm (register - offset)."""
        return self.get_power_register() - protocol.POWER_DBM_OFFSET

    def set_power_register(self, register: int) -> None:
        """``N1,<value>`` — set the raw TX power register (0x00..0x1B)."""
        if not protocol.MIN_POWER_REGISTER <= register <= protocol.MAX_POWER_REGISTER:
            raise ValueError("power register out of range: 0x00..0x1B")
        self._transact(f"N1,{register:02X}", allow_empty=True)

    def set_power_dbm(self, dbm: int) -> None:
        """
        Set the TX power in dBm.

        The register maps as ``register = dBm + offset`` (offset 2 for the A/T
        series), so 20 dBm -> register 0x16. Out-of-range values are clamped to the
        register limits.
        """
        register = dbm + protocol.POWER_DBM_OFFSET
        register = max(protocol.MIN_POWER_REGISTER, min(register, protocol.MAX_POWER_REGISTER))
        self.set_power_register(register)

    def get_regulation(self) -> str:
        """``N4,00`` — read the current frequency-regulation code."""
        return self._strip_prefix(self._transact("N4,00"), "N")

    def set_regulation(self, code: str) -> None:
        """``N5,<code>`` — set the frequency regulation (see :class:`Regulation`)."""
        self._transact(f"N5,{code}", allow_empty=True)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_password(password: str) -> str:
        """Uppercase and zero-pad a password to 8 hex chars."""
        password = password.strip().upper()
        if password[:2] == "0X":
            password = password[2:]
        try:
            int(password, 16)
        except ValueError:
            raise ValueError(f"password is not valid hex: {password!r}")
        if len(password) > 8:
            raise ValueError("password must be at most 8 hex chars")
        return password.zfill(8)

    def _raise_unless_ok(self, payload: str, operation: str) -> None:
        """For K/L: raise on error/no-tag, return quietly on ``<OK>``."""
        if payload == "":
            raise NoTagError(f"no tag in RF field for {operation}")
        if payload in ("<OK>", "OK"):
            return
        self._parse_tag_error(payload)
        raise ProtocolError(f"unexpected {operation} reply: {payload!r}")

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> "RFIDReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def value_to_3hex(value: int) -> str:
    """Format a lock mask/action as exactly 3 uppercase hex digits."""
    return format(value, "03X")
