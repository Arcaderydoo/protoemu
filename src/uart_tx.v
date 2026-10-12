/*
 * Copyright (c) 2026 Akshay Kumar
 * SPDX-License-Identifier: Apache-2.0
 *
 * uart_tx -- 8N1 UART transmitter.
 *
 * Frame: 1 start bit (0), 8 data bits LSB first, 1 stop bit (1).
 * Each bit is held for exactly CLKS_PER_BIT clock cycles.
 *
 * Handshake: pulse `start` high for one cycle while `busy` is low.
 * `data` is captured on that cycle. A `start` pulse while busy is ignored.
 * `busy` rises on the cycle after the accepted start and falls when the
 * stop bit has been held for its full bit time.
 */

`default_nettype none

module uart_tx #(
    parameter integer CLKS_PER_BIT = 434   // 50 MHz / 115200 baud = 434.03
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       start,
    input  wire [7:0] data,
    output reg        tx,
    output wire       busy
);

  // Width of the baud counter, and its terminal value.  (CLKS_PER_BIT >= 2)
  localparam integer CW     = $clog2(CLKS_PER_BIT);
  localparam integer LAST_I = CLKS_PER_BIT - 1;
  localparam [CW-1:0] LAST  = LAST_I[CW-1:0];

  // Bits still to go after the current one: {stop, d7..d0}, LSB first.
  // (The start bit is driven directly, so it is never stored.)
  reg [8:0]    shreg;
  reg [3:0]    bits_left;   // bits still to send including the current one; 0 = idle
  reg [CW-1:0] baud_cnt;    // cycles elapsed in the current bit

  assign busy = (bits_left != 4'd0);

  wire bit_done = (baud_cnt == LAST);

  always @(posedge clk) begin
    if (!rst_n) begin
      tx        <= 1'b1;
      shreg     <= 9'h1FF;
      bits_left <= 4'd0;
      baud_cnt  <= {CW{1'b0}};
    end else if (!busy) begin
      tx       <= 1'b1;
      baud_cnt <= {CW{1'b0}};
      if (start) begin
        shreg     <= {1'b1, data};
        bits_left <= 4'd10;
        tx        <= 1'b0;             // start bit goes out on the next cycle
      end
    end else if (bit_done) begin
      baud_cnt  <= {CW{1'b0}};
      bits_left <= bits_left - 4'd1;
      shreg     <= {1'b1, shreg[8:1]};   // shift in 1s: line idles high
      tx        <= shreg[0];
    end else begin
      baud_cnt <= baud_cnt + 1'b1;
    end
  end

endmodule
