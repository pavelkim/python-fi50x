"""A scripted Transport for exercising the driver without hardware."""

from collections import deque

from fi50x.transport import Transport


class FakeTransport(Transport):
    """
    Records everything written and replays queued reader frames.

    Use :meth:`queue_reply` to enqueue a return message. Each reply is emitted as
    the reader would frame it on the wire (``<LF> text <CR><LF>``), i.e. as two
    ``read_line`` results: the bare leading ``<LF>`` and then ``text<CR><LF>``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.written = []          # list[bytes] — every write() payload
        self._lines = deque()      # queued read_line() results

    # -- Transport interface --------------------------------------------------

    def write(self, data: bytes) -> None:
        self.written.append(data)

    def read_line(self) -> bytes:
        return self._lines.popleft() if self._lines else b""

    # -- Test helpers ---------------------------------------------------------

    def queue_reply(self, text: str) -> "FakeTransport":
        """Queue one framed return message ``<LF> text <CR><LF>``."""
        self._lines.append(b"\x0a")
        self._lines.append(text.encode("ascii") + b"\x0d\x0a")
        return self

    def queue_raw_line(self, data: bytes) -> "FakeTransport":
        """Queue a raw read_line() result (for edge-case framing tests)."""
        self._lines.append(data)
        return self

    @property
    def last_command(self) -> str:
        """The ASCII body of the most recent framed command written."""
        raw = self.written[-1]
        # strip leading <LF> (0x0A) and trailing <CR> (0x0D)
        return raw[1:-1].decode("ascii")
