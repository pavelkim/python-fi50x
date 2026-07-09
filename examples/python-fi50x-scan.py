#!/usr/bin/env python3
"""
python-fi50x-scan.py — continuous inventory example for the ``fi50x`` library.

This doubles as an integration smoke test: it wires the driver to a real serial
port and runs a scan loop using only the public API.

Output modes:
    * changes (default): print only NEW and LOST tags, debounced against flaky
      reads (see --miss-tolerance).
    * stream           : print every tag seen on every sweep.

Configuration is taken from CLI flags, falling back to the environment (a local
``.env`` is read if python-decouple is installed).

Examples:
    ./python-fi50x-scan.py --port /dev/tty.usbmodem1234
    ./python-fi50x-scan.py --mode stream --power 20 --regulation 05
"""

import argparse
import logging
import sys

from fi50x import RFIDReader, ReaderError, TagTracker

try:  # optional: load config from .env like the rest of the project
    from decouple import config as _config
except ImportError:  # pragma: no cover - decouple is an optional dependency
    import os

    def _config(key, default=None, cast=None):
        value = os.environ.get(key, default)
        if cast is not None and value is not None:
            return cast(value)
        return value


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--port",
        default=_config("SERIAL_PORT", default="/dev/ttyUSB0"),
        help="serial device (default: %(default)s)",
    )
    parser.add_argument(
        "--baudrate", type=int,
        default=_config("BAUDRATE", default=38400, cast=int),
    )
    parser.add_argument(
        "--timeout", type=float,
        default=_config("TIMEOUT", default=0.5, cast=float),
        help="serial read timeout, seconds",
    )
    parser.add_argument(
        "--interval", type=float, default=0.1,
        help="delay between inventory sweeps, seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--mode", choices=["changes", "stream"], default="changes",
        help="report only new/lost tags, or every tag each sweep",
    )
    parser.add_argument(
        "--power", type=int, default=None,
        help="TX power in dBm to set at startup (-2..25)",
    )
    parser.add_argument(
        "--regulation", default=None,
        help="frequency regulation code to set at startup, e.g. 05 for EU",
    )
    parser.add_argument(
        "--slot-q", type=int, default=None,
        help="U<slotQ> slot-count parameter (1..10); default lets the reader choose",
    )
    parser.add_argument(
        "--miss-tolerance", type=int, default=2,
        help="sweeps a tag may be missed before it is reported LOST (changes mode)",
    )
    parser.add_argument(
        "--no-verify-crc", action="store_true",
        help="do not compute the EPC CRC-16 check",
    )
    parser.add_argument(
        "--log-level", default=_config("LOG_LEVEL", default="INFO"),
    )
    return parser.parse_args(argv)


def run(reader: RFIDReader, args: argparse.Namespace) -> None:
    """Drive the scan loop. Separated from I/O setup so it stays easy to follow."""
    log = logging.getLogger("fi50x-scan")
    log.info("firmware : %s", reader.firmware_version())
    log.info("reader id: %s", reader.refresh_reader_id())

    if args.regulation:
        reader.set_regulation(args.regulation)
        log.info("regulation set to %s", args.regulation)
    if args.power is not None:
        reader.set_power_dbm(args.power)
        log.info("power set to %d dBm", args.power)

    print(
        f"Scanning on {args.port} (mode={args.mode}, Ctrl+C to stop)...",
        file=sys.stderr,
    )
    tracker = TagTracker(miss_tolerance=args.miss_tolerance)
    for result in reader.stream_inventory(interval=args.interval, slot_q=args.slot_q):
        if args.mode == "stream":
            for tag in result.tags:
                suspect = " [CRC?]" if tag.crc_valid is False else ""
                print(f"  {tag.epc}{suspect}")
        else:
            delta = tracker.update(tag.epc for tag in result.tags)
            for epc in delta.new:
                print(f"+ NEW  {epc}")
            for epc in delta.lost:
                print(f"- LOST {epc}")


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("fi50x-scan")

    try:
        reader = RFIDReader.open(
            args.port,
            baudrate=args.baudrate,
            timeout=args.timeout,
            verify_crc=not args.no_verify_crc,
        )
    except Exception as exc:  # serial.SerialException et al.
        log.error("could not open reader on %s: %s", args.port, exc)
        return 1

    with reader:
        try:
            run(reader, args)
        except KeyboardInterrupt:
            print("\nstopped.", file=sys.stderr)
        except ReaderError as exc:
            log.error("reader error: %s", exc)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
