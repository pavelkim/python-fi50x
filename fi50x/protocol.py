"""
Protocol constants and helpers for the FI-50X ASCII-over-UART protocol.

Framing (from the "Command format" datasheet):
    * Command:        <LF> {command char} {args...} <CR>
    * Return message: <LF> {command char} {payload...} <CR><LF>
    * Unmatched cmd:  <LF> X <CR><LF>

All numeric arguments on the wire are **hexadecimal ASCII** (this is easy to get
wrong: "read 32 words" is ``R3,0,20`` and "write at address 12" is ``W3,C,2,..``).
"""

from enum import IntEnum

# Framing bytes.
LF = 0x0A  # <LF> — starts every command and every return message
CR = 0x0D  # <CR> — ends every command; return messages end with <CR><LF>

DEFAULT_BAUDRATE = 38400

# Reply the reader sends when it does not recognise a command.
INVALID_COMMAND_REPLY = "X"


class Bank(IntEnum):
    """Gen2 memory banks, as accepted by the R/W/T commands."""

    RESERVED = 0  # kill password (0x00-0x1F) + access password (0x20-0x3F)
    EPC = 1       # EPC-CRC (0x00-0x0F), EPC-PC (0x10-0x1F), EPC # (0x20-0x7F)
    TID = 2       # tag identification
    USER = 3      # user memory


# Word-length limits for R/W (in words). The datasheet text says 1..0x1E, but the
# vendor's own examples read a full 512-bit USER bank as 32 words (``R3,0,20``),
# so 0x20 is accepted in practice. We follow the working examples.
MIN_WORD_LENGTH = 0x01
MAX_WORD_LENGTH = 0x20

# Address range for R/W (in words).
MIN_ADDRESS = 0x0000
MAX_ADDRESS = 0x3FFF

# Select (T) bit-length range.
MIN_SELECT_BITS = 0x01
MAX_SELECT_BITS = 0x60

# TX power register range for N1 (``00``..``1B``). The register maps linearly to
# dBm as ``dBm = register - 2`` for the A/T series (see POWER_DBM_OFFSET).
MIN_POWER_REGISTER = 0x00
MAX_POWER_REGISTER = 0x1B
POWER_DBM_OFFSET = 2  # register = dBm + offset; dBm = register - offset


class Regulation:
    """Frequency-regulation codes for the N5 command (values are wire strings)."""

    US = "01"   # 902-928 MHz
    TW = "02"   # 922-928 MHz
    CN = "03"   # 920-925 MHz
    CN2 = "04"  # 840-845 MHz
    EU = "05"   # 865-868 MHz
    JP = "06"   # 916-921 MHz
    KR = "07"   # 917-921 MHz
    VN = "08"   # 918-923 MHz
    EU2 = "09"  # 916-920 MHz
    IN = "0A"   # 865-867 MHz


# Baud-rate codes for the NA command.
BAUDRATE_CODES = {
    4800: "0",
    9600: "1",
    14400: "2",
    19200: "3",
    38400: "4",
    57600: "5",
    115200: "6",
    230400: "7",
}


def frame(command: str) -> bytes:
    """Wrap an ASCII command body as ``<LF> {command} <CR>``."""
    return bytes([LF]) + command.encode("ascii") + bytes([CR])


def hexarg(value: int) -> str:
    """Format an integer argument as uppercase hex with no leading zeros."""
    return format(value, "X")
