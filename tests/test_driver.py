"""Driver tests against a scripted FakeTransport (no hardware required)."""

import pytest

from fi50x import (
    RFIDReader,
    Bank,
    Regulation,
    NoTagError,
    InvalidCommandError,
    MemoryLockedError,
    MemoryOverrunError,
    ProtocolError,
)
from tests.fake_transport import FakeTransport


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def reader(transport):
    # Disable CRC verification by default so tag payloads need not carry valid CRCs.
    return RFIDReader(transport, verify_crc=False)


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #

def test_firmware_version(reader, transport):
    transport.queue_reply("V0102,FI-50X")
    assert reader.firmware_version() == "0102,FI-50X"
    assert transport.last_command == "V"


def test_reader_id_is_cached(reader, transport):
    assert reader.reader_id is None  # always defined, even before first read
    transport.queue_reply("S01234567")
    assert reader.refresh_reader_id() == "01234567"
    assert reader.reader_id == "01234567"


def test_invalid_command_raises(reader, transport):
    transport.queue_reply("X")
    with pytest.raises(InvalidCommandError):
        reader.firmware_version()


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #

def test_query_epc_no_tag(reader, transport):
    # Nothing queued -> timeout -> empty payload -> None
    assert reader.query_epc() is None


def test_query_epc_parses_tag(reader, transport):
    transport.queue_reply("Q3000E28011606000020BADC0FFEE1234")
    tag = reader.query_epc()
    assert tag is not None
    assert tag.pc == "3000"
    assert tag.crc == "1234"
    assert tag.epc == "E28011606000020BADC0FFEE"


def test_inventory_drains_all_frames_and_dedupes(reader, transport):
    transport.queue_reply("U3000AAAA1111")
    transport.queue_reply("U3000BBBB2222")
    transport.queue_reply("U3000AAAA1111")  # duplicate
    transport.queue_reply("U")              # bare-U terminator
    result = reader.inventory()
    epcs = [t.epc for t in result.tags]
    assert epcs == ["AAAA", "BBBB"]
    assert transport.last_command == "U"


def test_inventory_slot_q_command(reader, transport):
    transport.queue_reply("U")  # immediate terminator
    reader.inventory(slot_q=4)
    # written[0] is the U4 command
    assert transport.written[0][1:-1].decode() == "U4"


# --------------------------------------------------------------------------- #
# Read — hex wire formatting is the important part
# --------------------------------------------------------------------------- #

def test_read_formats_address_and_length_as_hex(reader, transport):
    # 32 words -> 0x20; the reader must see "R3,0,20", not "R3,0,32"
    transport.queue_reply("R" + "A" * (32 * 4))
    result = reader.read(Bank.USER, 0, 32)
    assert transport.last_command == "R3,0,20"
    assert result.data == "A" * 128
    assert result.length == 32


def test_read_hex_address(reader, transport):
    transport.queue_reply("R" + "0" * 4)
    reader.read(Bank.USER, 12, 1)  # address 12 -> 0xC
    assert transport.last_command == "R3,C,1"


def test_read_no_tag_raises(reader, transport):
    with pytest.raises(NoTagError):
        reader.read(Bank.EPC, 0, 4)


def test_read_error_code_raises_typed(reader, transport):
    transport.queue_reply("R4")  # memory locked
    with pytest.raises(MemoryLockedError):
        reader.read(Bank.USER, 0, 1)


def test_read_wrong_length_is_protocol_error(reader, transport):
    # A 1-word read expects 4 hex chars; "AAB" (3 chars) is neither data nor an
    # error code, so it is a protocol error.
    transport.queue_reply("RAAB")
    with pytest.raises(ProtocolError):
        reader.read(Bank.USER, 0, 1)


# --------------------------------------------------------------------------- #
# Write — the leading-zero data bug + hex formatting
# --------------------------------------------------------------------------- #

def test_write_preserves_leading_zero_data(reader, transport):
    transport.queue_reply("W<OK>")
    result = reader.write(Bank.USER, 0, "00001111")
    # The old code's lstrip('0X') mangled this to "1111"; it must stay intact.
    assert transport.last_command == "W3,0,2,00001111"
    assert result.ok is True
    assert result.words_written == 2


def test_write_strips_only_real_0x_prefix(reader, transport):
    transport.queue_reply("W<OK>")
    reader.write(Bank.USER, 0, "0x00001111")
    assert transport.last_command == "W3,0,2,00001111"


def test_write_hex_address(reader, transport):
    transport.queue_reply("W<OK>")
    reader.write(Bank.USER, 12, "AAAABBBB")  # address 12 -> 0xC, 2 words
    assert transport.last_command == "W3,C,2,AAAABBBB"


def test_write_length_mismatch_raises(reader, transport):
    with pytest.raises(ValueError):
        reader.write(Bank.USER, 0, "AAAA", length=2)


def test_write_bad_word_boundary_raises(reader, transport):
    with pytest.raises(ValueError):
        reader.write(Bank.USER, 0, "AAA")  # not a multiple of 4


def test_write_overrun_with_words_written(reader, transport):
    transport.queue_reply("3Z03")  # error 3 after writing 3 words
    with pytest.raises(MemoryOverrunError) as exc:
        reader.write(Bank.USER, 0, "AAAABBBBCCCCDDDD")
    assert exc.value.words_written == 3


def test_write_word_count_reply(reader, transport):
    transport.queue_reply("Z02")  # firmware reports 2 words written
    result = reader.write(Bank.USER, 0, "AAAABBBB")
    assert result.ok is True
    assert result.words_written == 2


# --------------------------------------------------------------------------- #
# Power / regulation
# --------------------------------------------------------------------------- #

def test_set_power_dbm_maps_with_offset(reader, transport):
    reader.set_power_dbm(20)  # register = 20 + 2 = 0x16
    assert transport.last_command == "N1,16"


def test_set_power_dbm_clamps(reader, transport):
    reader.set_power_dbm(100)  # clamps to register 0x1B
    assert transport.last_command == "N1,1B"


def test_get_power_register_and_dbm(reader, transport):
    transport.queue_reply("N16")
    assert reader.get_power_register() == 0x16
    transport.queue_reply("N16")
    assert reader.get_power_dbm() == 0x16 - 2


def test_set_regulation_command(reader, transport):
    reader.set_regulation(Regulation.EU)
    assert transport.last_command == "N5,05"


# --------------------------------------------------------------------------- #
# Tag management
# --------------------------------------------------------------------------- #

def test_kill_command_and_ok(reader, transport):
    transport.queue_reply("K<OK>")
    reader.kill("01020304", recom=0)
    assert transport.last_command == "K01020304,0"


def test_kill_pads_password(reader, transport):
    transport.queue_reply("K<OK>")
    reader.kill("A1A2")  # -> zero-padded to 8 hex chars
    assert transport.last_command == "K0000A1A2,0"


def test_lock_epc_write_formats_3hex(reader, transport):
    transport.queue_reply("L<OK>")
    reader.lock_epc_write()
    assert transport.last_command == "L020,020"


def test_lock_error_is_typed(reader, transport):
    transport.queue_reply("L4")
    with pytest.raises(MemoryLockedError):
        reader.unlock_epc_write()


def test_set_access_password_command(reader, transport):
    transport.queue_reply("P")
    reader.set_access_password("A1A2A3A4")
    assert transport.last_command == "PA1A2A3A4"


def test_select_command_format(reader, transport):
    reader.select(Bank.EPC, 0x20, 0x08, "AB")
    assert transport.last_command == "T1,20,8,AB"


# --------------------------------------------------------------------------- #
# Read-with-EPC (QR)
# --------------------------------------------------------------------------- #

def test_read_with_epc_single_tag(reader, transport):
    transport.queue_reply("Q3000AAAA1111,RDEADBEEF")
    results = reader.read_with_epc(Bank.USER, 0, 2)
    assert transport.written[0][1:-1].decode() == "Q,R3,0,2"
    assert len(results) == 1
    assert results[0].tag.epc == "AAAA"
    assert results[0].data == "DEADBEEF"
