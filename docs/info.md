<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

ProtoEmu is being built as a programmable protocol emulator for the Jane Street protocol emulator ASIC
competition. This is **milestone 0**: a fixed-rate 8N1 UART transmitter that later milestones replace with
PIO-style programmable cores.

- `uart_tx` sends 1 start bit (0), 8 data bits LSB first, and 1 stop bit (1). Each bit lasts exactly
  `CLKS_PER_BIT` = 434 clocks, which gives 115207 baud from a 50 MHz clock (0.006% error).
- SEND is asynchronous to the clock, so it passes through a 2-flop synchroniser and an edge detector. Each
  rising edge of SEND starts one frame. A SEND edge that arrives while BUSY is high is ignored.
- DATA is captured on the cycle the frame starts. It is not synchronised, so it must already be stable before
  SEND rises.
- All state resets from `rst_n`.

| Pin | Name | Direction | Function |
| --- | --- | --- | --- |
| `ui[7:0]` | DATA | in | Byte to send |
| `uio[0]` | SEND | in | Rising edge starts a frame |
| `uo[0]` | TX | out | UART line, idles high |
| `uo[1]` | BUSY | out | High while a frame is in flight |

## How to test

1. Set the clock to 50 MHz and pulse `rst_n` low.
2. Put a byte on `ui[7:0]`.
3. Raise `uio[0]` (SEND) and hold it until `uo[1]` (BUSY) goes high, then lower it.
4. Read `uo[0]` (TX) with a 3.3 V USB-UART adapter, or a logic analyser, at 115200 8N1.

## External hardware

A 3.3 V USB-UART adapter or a logic analyser on `uo[0]`.
