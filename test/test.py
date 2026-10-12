# SPDX-FileCopyrightText: © 2026 Akshay Kumar
# SPDX-License-Identifier: Apache-2.0
"""
Milestone 0 tests: UART TX on uo_out[0].

Every test talks to the design only through its top-level pins, so the same
file runs on the RTL (`make`) and on the gate-level netlist (`make GATES=yes`).

Conventions
  * The driver changes inputs on the FALLING clock edge and the monitor samples
    outputs on the falling edge too. Flops update on the rising edge, so both
    sides always see settled values: no races, no ReadOnly phases needed.
  * The UART monitor is cycle-accurate: it checks that every bit window is
    exactly CLKS_PER_BIT cycles long and constant across the whole window,
    not just correct at the mid-bit sample point.
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

CLK_PERIOD_NS = 20            # 50 MHz, must match info.yaml clock_hz
CLKS_PER_BIT = 434            # must match the RTL parameter default
BAUD_TARGET = 115_200
SEND_TO_START_MAX = 5         # cycles from SEND rising to the start bit


# ----------------------------------------------------------------------------
# Pin helpers
# ----------------------------------------------------------------------------
def tx(dut) -> int:
    return dut.uo_out.value.to_unsigned() & 1


def busy(dut) -> int:
    return (dut.uo_out.value.to_unsigned() >> 1) & 1


async def setup(dut):
    """Start the clock and apply a reset with all inputs at 0."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


async def send_byte(dut, value: int) -> int:
    """Put `value` on DATA, raise SEND until BUSY rises, then lower SEND.

    Returns the number of cycles from SEND rising to the start bit.
    """
    await FallingEdge(dut.clk)
    dut.ui_in.value = value
    await FallingEdge(dut.clk)
    dut.uio_in.value = 1
    latency = 0
    while tx(dut) == 1:
        await FallingEdge(dut.clk)
        latency += 1
        assert latency <= SEND_TO_START_MAX, "start bit did not appear after SEND"
    while busy(dut) == 0:
        await FallingEdge(dut.clk)
    dut.uio_in.value = 0
    return latency


async def wait_idle(dut, timeout_cycles: int = 12 * CLKS_PER_BIT):
    for _ in range(timeout_cycles):
        if busy(dut) == 0:
            return
        await FallingEdge(dut.clk)
    raise AssertionError("BUSY never fell")


# ----------------------------------------------------------------------------
# UART monitor: decodes 8N1 frames and checks bit timing cycle by cycle
# ----------------------------------------------------------------------------
class UartMonitor:
    def __init__(self, dut, clks_per_bit: int):
        self.dut = dut
        self.n = clks_per_bit
        self.frames: list[int] = []
        self.errors: list[str] = []

    async def _sample(self) -> int:
        await FallingEdge(self.dut.clk)
        val = self.dut.uo_out.value
        if not val.is_resolvable:
            self.errors.append(f"TX line is X/Z: {val}")
            return 1
        return val.to_unsigned() & 1

    async def _window(self, first: int) -> int | None:
        """Collect one bit window; return its value, or None if it changed."""
        samples = [first] + [await self._sample() for _ in range(self.n - 1)]
        if len(set(samples)) != 1:
            return None
        return samples[0]

    async def run(self):
        while True:
            first = await self._sample()
            if first == 1:
                continue                       # line idle
            windows = [await self._window(first)]
            for _ in range(9):                 # 8 data bits + stop bit
                windows.append(await self._window(await self._sample()))
            frame_no = len(self.frames) + len(self.errors)
            if None in windows:
                self.errors.append(f"frame {frame_no}: a bit changed inside its window")
            elif windows[0] != 0:
                self.errors.append(f"frame {frame_no}: short start bit")
            elif windows[9] != 1:
                self.errors.append(f"frame {frame_no}: framing error (stop bit low)")
            else:
                self.frames.append(sum(b << i for i, b in enumerate(windows[1:9])))


def check(mon: UartMonitor, expected: list[int]):
    assert not mon.errors, "monitor errors:\n  " + "\n  ".join(mon.errors)
    got = [f"{b:02x}" for b in mon.frames]
    exp = [f"{b:02x}" for b in expected]
    assert got == exp, f"received {got}, expected {exp}"


# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------
@cocotb.test()
async def test_idle_after_reset(dut):
    """TX idles high, BUSY low, and all uio pins are inputs."""
    await setup(dut)
    assert dut.uio_oe.value.to_unsigned() == 0, "uio pins must all be inputs"
    for _ in range(2 * CLKS_PER_BIT):
        assert tx(dut) == 1, "TX must idle high"
        assert busy(dut) == 0, "BUSY must be low when idle"
        await FallingEdge(dut.clk)


@cocotb.test()
async def test_directed_bytes(dut):
    """Corner-case bytes come out with exact bit timing and bounded latency."""
    await setup(dut)
    mon = UartMonitor(dut, CLKS_PER_BIT)
    cocotb.start_soon(mon.run())

    expected = [0x00, 0xFF, 0x55, 0xAA, 0x01, 0x80, 0x0F, 0xF0]
    for b in expected:
        latency = await send_byte(dut, b)
        assert latency <= SEND_TO_START_MAX
        await wait_idle(dut)
    await ClockCycles(dut.clk, 2 * CLKS_PER_BIT)
    check(mon, expected)

    baud = 1e9 / (CLK_PERIOD_NS * CLKS_PER_BIT)
    err = abs(baud - BAUD_TARGET) / BAUD_TARGET
    dut._log.info(f"baud {baud:.0f} ({err * 100:.3f}% error vs {BAUD_TARGET})")
    assert err < 0.02, "baud error above 2%"


@cocotb.test()
async def test_random_bytes(dut):
    """Random bytes with random idle gaps, including zero gap (back-to-back)."""
    await setup(dut)
    mon = UartMonitor(dut, CLKS_PER_BIT)
    cocotb.start_soon(mon.run())

    expected = [random.randrange(256) for _ in range(24)]
    for b in expected:
        await send_byte(dut, b)
        await wait_idle(dut)
        gap = random.choice([0, 0, 1, random.randrange(2 * CLKS_PER_BIT)])
        await ClockCycles(dut.clk, gap)
    await ClockCycles(dut.clk, 2 * CLKS_PER_BIT)
    check(mon, expected)


@cocotb.test()
async def test_send_while_busy_is_ignored(dut):
    """A second SEND during a frame must not start or corrupt a frame."""
    await setup(dut)
    mon = UartMonitor(dut, CLKS_PER_BIT)
    cocotb.start_soon(mon.run())

    await send_byte(dut, 0x3C)
    await ClockCycles(dut.clk, 3 * CLKS_PER_BIT)   # mid-frame
    await send_byte_no_wait(dut, 0xC3)
    await wait_idle(dut)
    await ClockCycles(dut.clk, 2 * CLKS_PER_BIT)
    check(mon, [0x3C])


async def send_byte_no_wait(dut, value: int):
    """Pulse SEND for a few cycles without waiting for the start bit."""
    await FallingEdge(dut.clk)
    dut.ui_in.value = value
    await FallingEdge(dut.clk)
    dut.uio_in.value = 1
    await ClockCycles(dut.clk, 4)
    await FallingEdge(dut.clk)
    dut.uio_in.value = 0


@cocotb.test()
async def test_reset_mid_frame(dut):
    """Reset aborts a frame cleanly, and the next frame is correct."""
    await setup(dut)
    await send_byte(dut, 0x00)                      # TX low for 9 bit times
    await ClockCycles(dut.clk, 3 * CLKS_PER_BIT)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    await FallingEdge(dut.clk)                      # one rising edge in reset
    assert tx(dut) == 1, "TX must return high in reset"
    assert busy(dut) == 0, "BUSY must clear in reset"
    await ClockCycles(dut.clk, 5)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    mon = UartMonitor(dut, CLKS_PER_BIT)
    cocotb.start_soon(mon.run())
    await send_byte(dut, 0xA5)
    await wait_idle(dut)
    await ClockCycles(dut.clk, 2 * CLKS_PER_BIT)
    check(mon, [0xA5])
