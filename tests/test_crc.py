"""Tests for the Gen2 CRC-16 implementation."""

from fi50x import crc


def test_crc16_is_deterministic():
    data = bytes.fromhex("3000E28011606000020B5C11")
    assert crc.crc16(data) == crc.crc16(data)


def test_crc16_empty():
    assert crc.crc16(b"") == 0xFFFF


def test_verify_epc_round_trip():
    # Build a PC+EPC, compute its CRC with the same routine, and confirm verify
    # accepts the matching CRC and rejects a corrupted one.
    pc = "3000"
    epc = "E28011606000020BADC0FFEE"
    computed = crc.crc16(bytes.fromhex(pc + epc))
    crc_hex = f"{computed:04X}"

    assert crc.verify_epc(pc, epc, crc_hex) is True
    wrong = f"{(computed ^ 0x0001):04X}"
    assert crc.verify_epc(pc, epc, wrong) is False


def test_verify_epc_bad_hex_is_false():
    assert crc.verify_epc("ZZZZ", "EPC!", "----") is False
