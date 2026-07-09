# FI-50X Command Exchange Specification

Reference for the FI-50X UHF RFID reader (ISO-18000-6C / EPC Gen2) ASCII-over-UART
protocol, transcribed from the vendor datasheets in [`doc/`](.). This is the
protocol the [`fi50x`](../fi50x) driver library implements.

## Absolute maximum ratings

| Parameter                | Value           |
| ------------------------ | --------------- |
| Max storage temperature  | +120 °C         |
| Min storage temperature  | −60 °C          |
| Power supply voltage      | −0.1 V to +5.5 V |
| Electrostatic discharge  | 1 kV            |

## Interface characteristics

**UART interface (USB to UART).** The host sends a command and waits for the
reader to return a message.

| Parameter  | Value            |
| ---------- | ---------------- |
| Baud rate  | 38400 (default)  |
| Data bits  | 8                |
| Stop bits  | 1                |
| Parity     | none             |

## ASCII protocol framing

Commands and return messages are transmitted in **ASCII**. Numeric arguments are
**hexadecimal** (this is easy to get wrong — "read 32 words" is `R3,0,20` and
"write at address 12" is `W3,C,2,…`).

* **Command** — starts with a command character and arguments, ends with `<CR>` (`0x0D`).
* **Return message** — starts with `<LF>` (`0x0A`), includes the command's first character, ends with `<CR><LF>`.
* If a command does not match: return = `<LF>X<CR><LF>`.

```
PC/Host → <LF>S<CR>
Reader  → <LF>S01234567<CR><LF>
```

## Command overview

| Command | Return message | Description |
| ------- | -------------- | ----------- |
| **V** | `Vxxyy,<message>`<br>`xx`: major, `yy`: minor, `<message>`: other info | Reader firmware version |
| **S** | `S01234567` (`01234567` = reader ID) | Reader ID |
| **Q** | `Q<none or EPC>` — none: no tag; EPC: `PC+EPC+CRC16` | Query single tag EPC |
| **R\<bank>,\<address>,\<length>** | `R<none/read data>` or `<error code>` | Read tag memory<br>bank: 0=reserved, 1=EPC, 2=TID, 3=USER<br>address: 0–3FFF<br>length: 1–1E words |
| **W\<bank>,\<address>,\<length>,\<data>** | `W<none/<OK>>` or `<error code>`<br>`Z00`–`Z1F`: words written<br>`3Z00`–`3Z1F`: error code + words written | Write tag memory |
| **K\<password>,\<recom>** | `K<none/<OK>>` or `<error code>` | Kill tag<br>password: `00000000`–`FFFFFFFF`<br>recom: 0–7 |
| **L\<mask>,\<action>** | `L<none/<OK>>` or `<error code>` | Lock memory<br>mask: `000`–`3FF`, action: `000`–`3FF` |
| **P\<password>** | `P` | Set access password (one-time, for the next R/W/L)<br>password: `00000000`–`FFFFFFFF` |
| **U** | `U<none/EPC>` | Multi-tag EPC inventory |
| **U\<slot Q>** | `U<none/EPC>` | Multi-tag inventory with slot count Q (1–0A) |
| **T\<bank>,\<bit address>,\<bit length>,\<bit data>** | `T` | Select matching tag<br>bit address: 0–3FFF, bit length: 1–60 |
| **G1 / G0 / G2** | `G1` / `G0` / `G2` | Start / end / run command logging (external TACT switch) |
| **N0,00** | `N<value>` | Read RF power level |
| **N1,\<value>** | `<NULL>` | Set RF power, `(-2~25dBm)` → `00`–`1B` |
| **N4,00** | `N<value>` | Read regulation |
| **N5,\<value>** | `<NULL>` | Set regulation (see table below) |
| **N6,00 / N7,\<value>** | `N<value>` | Get / set GPIO I/O config<br>mask & setting nibbles: 4=pin10, 2=pin11, 1=pin14 |
| **N8,00 / N9,\<value>** | `N<value>` | Read / write GPIO pins (same nibble encoding) |
| **NA,\<value>** | `N<value>` | Set UART baud rate (applies after the reply) |
| **UR: U\<slot Q>,R\<bank>,\<address>,\<length>** | `U<EPC>,R<DATA>` or `<error code>` | Multi-band data read with EPC (multi-tag)<br>slot Q: 0–10 |
| **QR: Q,R\<bank>,\<address>,\<length>** | `Q<EPC>,R<DATA>` or `<error code>` | Multi-band data read with EPC (single-tag) |

### Error codes (R / W / K / L / UR / QR)

| Code | Meaning              |
| ---- | -------------------- |
| `0`  | other error          |
| `3`  | memory overrun       |
| `4`  | memory locked        |
| `B`  | insufficient power   |
| `F`  | non-specific error   |

### Regulation codes (N5)

| Code | Region | Frequency     |
| ---- | ------ | ------------- |
| `01` | US     | 902–928 MHz   |
| `02` | TW     | 922–928 MHz   |
| `03` | CN     | 920–925 MHz   |
| `04` | CN2    | 840–845 MHz   |
| `05` | EU     | 865–868 MHz   |
| `06` | JP     | 916–921 MHz   |
| `07` | KR     | 917–921 MHz   |
| `08` | VN     | 918–923 MHz   |
| `09` | EU2    | 916–920 MHz   |
| `0A` | IN     | 865–867 MHz   |

### Baud-rate codes (NA)

| Code | Baud   | Code | Baud    |
| ---- | ------ | ---- | ------- |
| `0`  | 4800   | `4`  | 38400   |
| `1`  | 9600   | `5`  | 57600   |
| `2`  | 14400  | `6`  | 115200  |
| `3`  | 19200  | `7`  | 230400  |

## Examples

**Read TID memory** — start address 0, 4 words:

```
Host   : <LF>R2,0,4<CR>          hex: 0A 52 32 2C 30 2C 34 0D
Reader : <LF>R123456789ABCDEF0<CR><LF>
```

**Write USER memory** — start address 0x0C, 2 words, data `0xAAAABBBB`:

```
Host   : <LF>W3,C,2,AAAABBBB<CR> hex: 0A 57 33 2C 43 2C 32 2C 41 41 41 41 42 42 42 42 0D
Reader : <LF>W<OK><CR><LF>       hex: 0A 57 3C 4F 4B 3E 0D 0A
```

## Command quick reference

| Command | HEX | ASCII |
| ------- | --- | ----- |
| FW version | `0A 56 0D` | `<LF>V<CR>` |
| Reader ID | `0A 53 0D` | `<LF>S<CR>` |
| Query EPC | `0A 51 0D` | `<LF>Q<CR>` |
| Multi EPC | `0A 55 0D` | `<LF>U<CR>` |
| Read power | `0A 4E 30 2C 30 30 0D` | `<LF>N0,00<CR>` |
| Write power (0x14) | `0A 4E 31 2C 31 34 0D` | `<LF>N1,14<CR>` |
| Read TID (addr 0, 6 words) | `0A 52 32 2C 30 2C 36 0D` | `<LF>R2,0,6<CR>` |
| Read EPC-PC word | `0A 52 31 2C 31 2C 31 0D` | `<LF>R1,1,1<CR>` |
| Read EPC (addr 0, 8 words) | `0A 52 31 2C 30 2C 38 0D` | `<LF>R1,0,8<CR>` |
| Read USER (addr 0, 32 words) | `0A 52 33 2C 30 2C 32 30 0D` | `<LF>R3,0,20<CR>` |
| Read reserved (kill+access pwd) | `0A 52 30 2C 30 2C 32 0D` | `<LF>R0,0,2<CR>` |
| Write EPC-PC word | `0A 57 31 2C 31 2C 31 2C 33 30 30 30 0D` | `<LF>W1,1,1,3000<CR>` |
| Write EPC (addr 2, 6 words) | `0A 57 31 2C 32 2C 36 2C …` | `<LF>W1,2,6,000011112222333344445555<CR>` |
| Write USER (addr 0, 1 word) | `0A 57 33 2C 30 2C 31 2C 30 30 30 30 0D` | `<LF>W3,0,1,0000<CR>` |
| Write USER (addr 0, 8 words) | `0A 57 33 2C 30 2C 38 2C …` | `<LF>W3,0,8,00001111222233334444555566667777<CR>` |
| Write reserved kill pwd | `0A 57 30 2C 30 2C 32 2C 30 31 30 32 30 33 30 34 0D` | `<LF>W0,0,2,01020304<CR>` |
| Write access pwd | `0A 57 30 2C 32 2C 32 2C 31 32 33 34 35 36 37 38 0D` | `<LF>W0,2,2,12345678<CR>` |
| Write reserved kill+access pwd | `0A 57 30 2C 30 2C 34 2C …` | `<LF>W0,0,4,01020304A1A2A3A4<CR>` |
| Access password | `0A 50 41 31 41 32 41 33 41 34 0D` | `<LF>PA1A2A3A4<CR>` |
| Kill | `0A 4B 30 31 30 32 30 33 30 34 2C 30 0D` | `<LF>K01020304,0<CR>` |
| Lock EPC write (mask 020, action 020) | `0A 4C 30 32 30 2C 30 32 30 0D` | `<LF>L020,020<CR>` |
| Unlock EPC write (mask 020, action 000) | `0A 4C 30 32 30 2C 30 30 30 0D` | `<LF>L020,000<CR>` |
| US 902–928 | `0A 4E 35 2C 30 31 0D` | `<LF>N5,01<CR>` |
| TW 922–928 | `0A 4E 35 2C 30 32 0D` | `<LF>N5,02<CR>` |
| CN 920–925 | `0A 4E 35 2C 30 33 0D` | `<LF>N5,03<CR>` |
| CN2 840–845 | `0A 4E 35 2C 30 34 0D` | `<LF>N5,04<CR>` |
| EU 865–868 | `0A 4E 35 2C 30 35 0D` | `<LF>N5,05<CR>` |
| JP 916–921 | `0A 4E 35 2C 30 36 0D` | `<LF>N5,06<CR>` |
| KR 917–921 | `0A 4E 35 2C 30 37 0D` | `<LF>N5,07<CR>` |
| VN 918–923 | `0A 4E 35 2C 30 38 0D` | `<LF>N5,08<CR>` |
| EU2 916–920 | `0A 4E 35 2C 30 39 0D` | `<LF>N5,09<CR>` |
| IN 865–867 | `0A 4E 35 2C 30 41 0D` | `<LF>N5,0A<CR>` |

## Memory map (Gen2)

Bank/address layout from the datasheet. Note the addresses below are **bit
offsets**; the R/W commands use **word** addresses (1 word = 16 bits).

| Bank     | Address     | Description                   | Memory  | Bits |
| -------- | ----------- | ----------------------------- | ------- | ---- |
| User     | 00h–1FFh    | User                          | NVM     | 512  |
| TID      | 70h–BFh     | Device configuration          | ROM-NVM | 80   |
|          | 60h–6Fh     | Mask unique identifier        | ROM     | 16   |
|          | 20h–5Fh     | Unique tag ID (unalterable)   | NVM     | 64   |
|          | 00h–1Fh     | TID EPC/TMD/TMDID/TMN         | ROM     | 32   |
| EPC      | 20h–7Fh     | EPC #                         | NVM     | 96   |
|          | 10h–1Fh     | EPC-PC                        | NVM     | 16   |
|          | 00h–0Fh     | EPC-CRC                       | RAM     | 16   |
| Reserved | 20h–3Fh     | Access password (EPC optional)| NVM     | 32   |
|          | 00h–1Fh     | Kill password                 | NVM     | 32   |

## CRC-16 (EPC)

Polynomial `x^16 + x^12 + x^5 + 1` (`0x1021`), initial value `0xFFFF`, residue
`0x1D0F`. The reference implementation and verification live in
[`fi50x/crc.py`](../fi50x/crc.py); a C/C#/MFC sample is in
[`doc/CRC16 sample Code.txt`](CRC16%20sample%20Code.txt).
