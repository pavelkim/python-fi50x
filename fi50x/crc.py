"""
Gen2 CRC-16 for EPC verification.

Polynomial: x^16 + x^12 + x^5 + 1 (0x1021), initial value 0xFFFF, residue 0x1D0F.
This is a faithful port of the vendor-supplied C#/Java ``CRC16`` (see
``doc/CRC16 sample Code.txt`` and ``ReaderService.Format.crc16``), including its
quirk of skipping the first byte when it is zero.

CRC verification is best-effort: a mismatch means the EPC read is suspect, but the
driver surfaces it rather than discarding the tag, so callers decide what to do.
"""

CRC_RESIDUE = 0x1D0F


def crc16(data: bytes) -> int:
    """Compute the FI-50X Gen2 CRC-16 over ``data``."""
    crc = 0xFFFF
    polynomial = 0x1021

    if not data:
        return crc & 0xFFFF

    # Vendor quirk: when the first byte is zero, skip it (start at bit 8 / byte 1).
    x, y = (8, 1) if data[0] == 0 else (0, 0)

    j = y
    for i in range(x, len(data) * 8):
        if i % 8 == 0:
            crc ^= (data[j] << 8) & 0xFF00
            j += 1
        if crc & 0x8000:
            crc = ((crc << 1) & 0xFFFE) ^ polynomial
        else:
            crc = (crc << 1) & 0xFFFE
    return crc & 0xFFFF


def verify_epc(pc_hex: str, epc_hex: str, crc_hex: str) -> bool:
    """
    Verify a tag's CRC-16 against its PC + EPC.

    Args:
        pc_hex: the 4-hex-char PC word.
        epc_hex: the EPC hex string.
        crc_hex: the 4-hex-char CRC word returned by the reader.

    Returns:
        True if the computed CRC matches ``crc_hex``.
    """
    try:
        pc_epc = bytes.fromhex(pc_hex + epc_hex)
        expected = int(crc_hex, 16)
    except ValueError:
        return False
    return crc16(pc_epc) == expected
