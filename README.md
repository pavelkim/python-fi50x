# python-fi50x

A transport-agnostic Python driver for the **FI-50X UHF RFID reader**
(ISO-18000-6C / EPC Gen2) over its ASCII-over-UART protocol.

The library knows only the reader protocol — framing, the command set, typed
responses, error-code handling and CRC-16 verification. It talks to a pluggable
transport, so the same driver runs against a real serial port or a scripted fake
in tests, and can be wrapped by any service (a RabbitMQ worker, a REST API, a CLI)
on top.

- **Import name:** `fi50x`
- **Distribution name:** `python-fi50x` (like `python-decouple` → `import decouple`)

## Features

- Inventory: single (`Q`) and multi-tag (`U`, `U<slotQ>`) EPC reads, drained to completion and de-duplicated
- Memory read/write (`R`/`W`) with correct **hex** address/length framing and word-length validation
- Tag management: access password (`P`), kill (`K`), lock/unlock (`L`), select/filter (`T`)
- Read-with-EPC (`UR`/`QR`), TX power and frequency-regulation get/set
- Typed results (`Tag`, `ReadResult`, `WriteResult`) and a typed exception hierarchy for reader error codes
- Gen2 CRC-16 verification of EPC reads
- `TagTracker` helper to turn inventory sweeps into new/lost tag events
- Thread-safe: a transport lock serialises full command/response transactions

Scope note: GPIO, frequency tuning, baud switching, command logging and the `AA`
binary protocol are **not** implemented yet. See [doc/PROTOCOL.md](doc/PROTOCOL.md)
for the complete protocol reference.

## Installation

```bash
pip install python-fi50x
```

Requires Python ≥ 3.8 and a serial connection to the reader (USB-UART). From
source:

```bash
git clone https://github.com/pavelkim/python-fi50x
cd python-fi50x
pip install -e .[dev]
```

## Quickstart

```python
from fi50x import RFIDReader, Bank, Regulation

# Open the serial port (default baud 38400).
reader = RFIDReader.open("/dev/ttyUSB0")

print("firmware:", reader.firmware_version())
print("reader id:", reader.refresh_reader_id())

# Optional configuration
reader.set_regulation(Regulation.EU)   # 865–868 MHz
reader.set_power_dbm(20)               # register = dBm + 2, handled for you

# Inventory — read every tag currently in the field
for tag in reader.inventory().tags:
    print(tag.epc, "crc_ok" if tag.crc_valid else "crc?")

# Read 4 words of USER memory, then write two words back
data = reader.read(Bank.USER, address=0, length=4).data
reader.write(Bank.USER, address=0, data="DEADBEEF")   # leading zeros preserved

reader.close()
```

`RFIDReader` is also a context manager (`with RFIDReader.open(port) as reader:`).
For tests or non-serial links, construct it directly with a `Transport`:
`RFIDReader(my_transport)`.

### Continuous scanning with new/lost detection

```python
from fi50x import RFIDReader, TagTracker

reader = RFIDReader.open("/dev/ttyUSB0")
tracker = TagTracker(miss_tolerance=2)   # tolerate a couple of missed sweeps

for result in reader.stream_inventory(interval=0.1):
    delta = tracker.update(tag.epc for tag in result.tags)
    for epc in delta.new:
        print("+ NEW ", epc)
    for epc in delta.lost:
        print("- LOST", epc)
```

A ready-to-run version of this is [python-fi50x-scan.py](python-fi50x-scan.py):

```bash
./python-fi50x-scan.py --port /dev/ttyUSB0 --mode changes   # only new/lost tags
./python-fi50x-scan.py --port /dev/ttyUSB0 --mode stream     # every tag, every sweep
./python-fi50x-scan.py --help
```

## Error handling

Reader error codes are raised as typed exceptions (all subclasses of
`ReaderError`), so callers can react to specific conditions:

```python
from fi50x import MemoryLockedError, InsufficientPowerError, NoTagError

try:
    reader.write(Bank.EPC, 2, "30001234")
except MemoryLockedError:
    ...   # bank is locked
except InsufficientPowerError:
    ...   # move the tag closer / raise power and retry
except NoTagError:
    ...   # nothing in the field
```

## Configuration

The example script reads config from CLI flags, falling back to environment
variables (a local `.env` is loaded if [python-decouple](https://pypi.org/project/python-decouple/)
is installed). See [.env.example](.env.example):

| Variable      | Default         | Meaning                              |
| ------------- | --------------- | ------------------------------------ |
| `SERIAL_PORT` | `/dev/ttyUSB0`  | Serial device                        |
| `BAUDRATE`    | `38400`         | UART baud rate                       |
| `TIMEOUT`     | `0.5`           | Serial read timeout (s)              |
| `TX_POWER`    | `20`            | TX power in dBm (−2…25)              |
| `REGULATION`  | `05`            | Regulation code (`05` = EU)          |

## Development

```bash
pip install -e .[dev]
pytest                 # run the test suite (no hardware needed — uses a fake transport)
tox                    # test across Python versions
tox -e build           # build the sdist + wheel into dist/
```

Tests run entirely against a scripted `FakeTransport`, so no reader is required.

## Protocol reference

The full FI-50X command specification — framing, every command, error codes,
regulation and baud tables, examples and the Gen2 memory map — is in
[doc/PROTOCOL.md](doc/PROTOCOL.md). Original vendor datasheets are in [doc/](doc/).

## License

[MIT](LICENSE) © Pavel Kim
