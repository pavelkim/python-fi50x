"""
Exception hierarchy for the FI-50X reader driver.

The reader signals failures with single-character error codes embedded in the
return message (see the "Command format" datasheet). Instead of returning those
codes as opaque strings, the driver raises typed exceptions so callers can react
to specific conditions (e.g. retry on insufficient power, surface a locked-memory
error to the operator).
"""

from typing import Optional


class ReaderError(Exception):
    """Base class for every error raised by the driver."""


class NoResponseError(ReaderError):
    """The reader did not reply within the serial timeout."""


class InvalidCommandError(ReaderError):
    """The reader replied ``<LF>X<CR><LF>`` (command not recognised)."""


class ProtocolError(ReaderError):
    """A reply was received but could not be parsed into the expected shape."""


class NoTagError(ReaderError):
    """No tag was in the RF field for an operation that required one."""


class TagError(ReaderError):
    """
    The reader returned one of the documented tag error codes.

    Attributes:
        code: the single-character error code as sent by the reader.
        words_written: for write operations, the number of words the reader
            reports it managed to write before failing (``3Z00``..``3Z1F``),
            otherwise ``None``.
    """

    code: str = ""

    def __init__(self, message: str, *, words_written: Optional[int] = None):
        super().__init__(message)
        self.words_written = words_written


class OtherError(TagError):
    """Error code ``0`` — other/unspecified error."""

    code = "0"


class MemoryOverrunError(TagError):
    """Error code ``3`` — the requested address/length exceeds tag memory."""

    code = "3"


class MemoryLockedError(TagError):
    """Error code ``4`` — the targeted memory is locked."""

    code = "4"


class InsufficientPowerError(TagError):
    """Error code ``B`` — not enough RF power to complete the operation."""

    code = "B"


class NonSpecificError(TagError):
    """Error code ``F`` — non-specific tag error."""

    code = "F"


# Maps the reader's single-character error codes to their exception classes.
ERROR_CODES = {
    "0": OtherError,
    "3": MemoryOverrunError,
    "4": MemoryLockedError,
    "B": InsufficientPowerError,
    "F": NonSpecificError,
}

# Human-readable descriptions, keyed by error code.
ERROR_DESCRIPTIONS = {
    "0": "other error",
    "3": "memory overrun",
    "4": "memory locked",
    "B": "insufficient power",
    "F": "non-specific error",
}


def error_for(code: str, *, words_written: Optional[int] = None) -> TagError:
    """Build the typed :class:`TagError` for a reader error ``code``."""
    code = code.upper()
    cls = ERROR_CODES.get(code, OtherError)
    description = ERROR_DESCRIPTIONS.get(code, f"unknown error code {code!r}")
    return cls(description, words_written=words_written)
