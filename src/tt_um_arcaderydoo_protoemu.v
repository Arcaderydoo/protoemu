/*
 * Copyright (c) 2026 Akshay Kumar
 * SPDX-License-Identifier: Apache-2.0
 *
 * Milestone 0: a fixed-baud UART transmitter on a Tiny Tapeout pin.
 * The programmable protocol cores replace this in later milestones;
 * uart_tx stays on as the golden reference for testing them.
 *
 * Pins
 *   ui_in[7:0]  DATA  byte to send (set it before raising SEND)
 *   uio_in[0]   SEND  rising edge starts one 8N1 frame (ignored while BUSY)
 *   uo_out[0]   TX    UART line, idles high
 *   uo_out[1]   BUSY  high while a frame is being sent
 */

`default_nettype none

module tt_um_arcaderydoo_protoemu #(
    parameter integer CLKS_PER_BIT = 434   // 50 MHz clock, 115200 baud
) (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  // ---------------------------------------------------------------
  // SEND comes from outside the chip, asynchronous to clk.
  // Two flops resolve metastability; the third gives the previous
  // value so we can detect the rising edge (one-cycle pulse).
  // DATA is not synchronised: the host must hold it stable from
  // before SEND rises until BUSY goes high, so it is never sampled
  // while changing.
  // ---------------------------------------------------------------
  reg [2:0] send_sync;

  always @(posedge clk) begin
    if (!rst_n) send_sync <= 3'b000;
    else        send_sync <= {send_sync[1:0], uio_in[0]};
  end

  wire send_pulse = send_sync[1] & ~send_sync[2];

  wire tx, busy;

  uart_tx #(
      .CLKS_PER_BIT(CLKS_PER_BIT)
  ) u_uart_tx (
      .clk  (clk),
      .rst_n(rst_n),
      .start(send_pulse),
      .data (ui_in),
      .tx   (tx),
      .busy (busy)
  );

  assign uo_out  = {6'b0, busy, tx};
  assign uio_out = 8'b0;
  assign uio_oe  = 8'b0;          // all uio pins are inputs

  // List all unused inputs to prevent warnings
  wire _unused = &{ena, uio_in[7:1], 1'b0};

endmodule
