"""
Transport layer for the FI-50X driver.

The driver talks to an abstract :class:`Transport` rather than to pyserial
directly, so the same driver can run against real hardware (:class:`SerialTransport`)
or a scripted fake in tests. The transport also owns the lock that serialises full
command/response transactions — critical once a scan loop and a command consumer
share one physical port.
"""

import abc
import threading
from typing import Optional

import serial

from .protocol import DEFAULT_BAUDRATE


class Transport(abc.ABC):
    """A byte-oriented, line-buffered link to the reader."""

    def __init__(self) -> None:
        # RLock so a driver method can nest transactions if it ever needs to.
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        """Held across a whole write+read transaction to serialise port access."""
        return self._lock

    @abc.abstractmethod
    def write(self, data: bytes) -> None:
        """Write raw bytes to the reader."""

    @abc.abstractmethod
    def read_line(self) -> bytes:
        """
        Read one line terminated by ``\\n`` (LF), or return ``b""`` on timeout.
        """

    def reset_input(self) -> None:
        """Discard any buffered inbound bytes. No-op by default."""

    def close(self) -> None:
        """Close the underlying link. No-op by default."""


class SerialTransport(Transport):
    """A :class:`Transport` backed by a pyserial port."""

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = 0.5,
    ) -> None:
        super().__init__()
        self._serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
        )

    @property
    def serial(self) -> serial.Serial:
        return self._serial

    def write(self, data: bytes) -> None:
        self._serial.write(data)

    def read_line(self) -> bytes:
        return self._serial.readline()

    def reset_input(self) -> None:
        self._serial.reset_input_buffer()

    def close(self) -> None:
        if self._serial.is_open:
            self._serial.close()
