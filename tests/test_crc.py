"""Tests for the Gen2 CRC-16 implementation."""

from fi50x import crc


def test_crc16_is_deterministic():
    data = bytes.fromhex("3000E28011606000020B5C11")
    assert crc.crc16(data) == crc.crc16(data)


def test_crc16_empty():
    assert crc.crc16(b"") == 0xFFFF


def test_crc16_ccitt_false_check_value():
    # Pins the algorithm: the standard CRC-16/CCITT-FALSE check value for the
    # ASCII string "123456789" is 0x29B1. (Gen2 stores this XOR 0xFFFF = GENIBUS.)
    assert crc.crc16(b"123456789") == 0x29B1


def test_verify_epc_round_trip():
    # A real Gen2 tag stores the *complement* of the raw CRC (GENIBUS xorout),
    # so build the stored CRC that way and confirm the residue check accepts it
    # and rejects a corrupted one.
    pc = "3000"
    epc = "E28011606000020BADC0FFEE"
    stored = crc.crc16(bytes.fromhex(pc + epc)) ^ 0xFFFF
    crc_hex = f"{stored:04X}"

    assert crc.verify_epc(pc, epc, crc_hex) is True
    wrong = f"{(stored ^ 0x0001):04X}"
    assert crc.verify_epc(pc, epc, wrong) is False


def test_verify_epc_bad_hex_is_false():
    assert crc.verify_epc("ZZZZ", "EPC!", "----") is False
