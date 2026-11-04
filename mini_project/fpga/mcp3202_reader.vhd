-- =============================================================================
-- mcp3202_reader.vhd
-- Task 3 (option B) : SPI master for the Microchip MCP3202 12-bit ADC
--
-- One conversion is started by every 'start' pulse (the hardware Fs tick), so
-- the sampling instant is locked to the FPGA clock -> no software jitter.
--
-- MCP3202 frame used (SPI mode 0,0, 3 x 8 = 24 SCLK, MSB first):
--   DIN  : 0000 0001 | SGL ODD MSBF 0 0000 | 0000 0000
--          (start)     SGL=1 single-ended, ODD=channel, MSBF=1
--   DOUT : ???? ???? | ???? 0 B11 B10 B9 B8 | B7 ... B0
--   -> result = last 12 bits received.
-- The ADC latches DIN on the rising edge and changes DOUT on the falling edge,
-- so this master drives DIN while SCLK is low and samples DOUT when it raises
-- SCLK.
--
-- Timing (defaults): SCLK = 1 MHz -> 24 us per conversion (+ CS setup/hold),
-- well inside the 62.5 us sample period at 16 kS/s.
-- MCP3202 max f_CLK: 0.9 MHz @ VDD=2.7 V, 1.8 MHz @ 5 V. At VDD = 3.3 V use
-- SCLK_HZ <= 1 MHz (set 500_000 if conversions look noisy / wrong).
--
-- Generic MCP_PART lets the same reader drive other Microchip SPI ADCs that
-- may be in the lab drawer (all use the same 24-clock frame, mode 0,0):
--   3202 : MCP3202  12 bit, 2 ch, DIP-8   (default)
--   3204 : MCP3204/MCP3208 12 bit, 4/8 ch  DIN = 0000 01 SGL D2 | D1 D0 ...
--   3008 : MCP3004/MCP3008 10 bit, 4/8 ch  DIN = 0000 0001 | SGL D2 D1 D0 ...
--          10-bit result is shifted left 2 -> still a 0..4095 code downstream
--   3201 : MCP3201  12 bit, 1 ch (IN+/IN-), NO DIN pin, 16-clock frame:
--          DOUT = Hi-Z Hi-Z null B11..B0 B1 -> result = bits 12..1 of the
--          16 received bits. Max f_CLK 0.8 MHz @ 2.7 V -> use SCLK <= 800 kHz
--          at 3.3 V (create_project.tcl does this automatically).
-- =============================================================================
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity mcp3202_reader is
  generic (
    CLK_HZ  : natural := 50_000_000;
    SCLK_HZ : natural := 1_000_000;
    CHANNEL : natural range 0 to 7 := 0;
    MCP_PART: natural := 3202              -- 3202 | 3201 | 3204 (=3208) | 3008 (=3004)
  );
  port (
    clk        : in  std_logic;
    rst        : in  std_logic;
    start      : in  std_logic;                      -- Fs tick
    busy       : out std_logic;
    data_valid : out std_logic;                      -- 1-clock pulse
    data       : out std_logic_vector(11 downto 0);
    -- MCP3202 pins
    adc_cs_n   : out std_logic;
    adc_sclk   : out std_logic;
    adc_din    : out std_logic;                      -- FPGA -> ADC DIN
    adc_dout   : in  std_logic                       -- ADC DOUT -> FPGA
  );
end entity;

architecture rtl of mcp3202_reader is
  constant HALF : natural := CLK_HZ / (2 * SCLK_HZ);   -- clocks per half SCLK
  constant NBIT : natural := 24;                        -- shift register width
  function frame_len(part : natural) return natural is
  begin
    if part = 3201 then return 16; else return 24; end if;
  end function;
  constant NCLK : natural := frame_len(MCP_PART);       -- SCLKs per conversion

  -- command word, MSB transmitted first
  function cmd_word(ch : natural; part : natural) return std_logic_vector is
    variable w : std_logic_vector(NBIT - 1 downto 0) := (others => '0');
    variable c : unsigned(2 downto 0);
  begin
    c := to_unsigned(ch, 3);
    if part = 3204 or part = 3208 then
      w(18) := '1';                -- start
      w(17) := '1';                -- SGL
      w(16) := c(2);               -- D2
      w(15) := c(1);               -- D1
      w(14) := c(0);               -- D0
    elsif part = 3008 or part = 3004 then
      w(16) := '1';                -- start
      w(15) := '1';                -- SGL
      w(14) := c(2);
      w(13) := c(1);
      w(12) := c(0);
    else                           -- MCP3202
      w(16) := '1';                -- start bit (last bit of byte 0)
      w(15) := '1';                -- SGL/DIFF = 1 (single ended)
      w(14) := c(0);               -- ODD/SIGN = channel
      w(13) := '1';                -- MSBF = 1
    end if;
    return w;
  end function;

  type state_t is (IDLE, CS_SETUP, CLK_LOW, CLK_HIGH, CS_HOLD);
  signal state   : state_t := IDLE;
  signal div_cnt : natural range 0 to HALF - 1 := 0;
  signal bit_cnt : natural range 0 to NBIT := 0;
  signal tx_sh   : std_logic_vector(NBIT - 1 downto 0) := (others => '0');
  signal rx_sh   : std_logic_vector(NBIT - 1 downto 0) := (others => '0');
  signal dout_s  : std_logic_vector(1 downto 0) := (others => '0');
  signal miss    : std_logic := '0';  -- start arrived while busy (should never happen)
begin
  assert HALF >= 2 report "SCLK_HZ too high for CLK_HZ" severity failure;

  process (clk)
  begin
    if rising_edge(clk) then
      data_valid <= '0';
      dout_s     <= dout_s(0) & adc_dout;   -- 2-FF sync of DOUT

      if rst = '1' then
        state    <= IDLE;
        adc_cs_n <= '1';
        adc_sclk <= '0';
        adc_din  <= '0';
        div_cnt  <= 0;
        bit_cnt  <= 0;
      else
        case state is
          when IDLE =>
            adc_cs_n <= '1';
            adc_sclk <= '0';
            if start = '1' then
              tx_sh    <= cmd_word(CHANNEL, MCP_PART);
              adc_cs_n <= '0';
              div_cnt  <= 0;
              bit_cnt  <= 0;
              state    <= CS_SETUP;
            end if;

          when CS_SETUP =>              -- t_SUCS (>= 100 ns), one half period
            if div_cnt = HALF - 1 then
              div_cnt <= 0;
              adc_din <= tx_sh(NBIT - 1);
              tx_sh   <= tx_sh(NBIT - 2 downto 0) & '0';
              state   <= CLK_LOW;
            else
              div_cnt <= div_cnt + 1;
            end if;

          when CLK_LOW =>               -- DIN stable, SCLK low
            if div_cnt = HALF - 1 then
              div_cnt  <= 0;
              adc_sclk <= '1';          -- rising edge: ADC latches DIN
              -- DOUT was updated by the ADC on the previous falling edge.
              -- Two sync stages = 40 ns delay, negligible vs 500 ns half period.
              rx_sh    <= rx_sh(NBIT - 2 downto 0) & dout_s(1);
              bit_cnt  <= bit_cnt + 1;
              state    <= CLK_HIGH;
            else
              div_cnt <= div_cnt + 1;
            end if;

          when CLK_HIGH =>
            if div_cnt = HALF - 1 then
              div_cnt  <= 0;
              adc_sclk <= '0';          -- falling edge: ADC shifts out next bit
              if bit_cnt = NCLK then
                state <= CS_HOLD;
              else
                adc_din <= tx_sh(NBIT - 1);
                tx_sh   <= tx_sh(NBIT - 2 downto 0) & '0';
                state   <= CLK_LOW;
              end if;
            else
              div_cnt <= div_cnt + 1;
            end if;

          when CS_HOLD =>
            if div_cnt = HALF - 1 then
              adc_cs_n   <= '1';        -- t_CSH >= 500 ns until next start
              adc_din    <= '0';
              if MCP_PART = 3201 then
                data <= rx_sh(12 downto 1);         -- skip trailing LSB-first bit
              elsif MCP_PART = 3008 or MCP_PART = 3004 then
                data <= rx_sh(9 downto 0) & "00";   -- 10 bit -> 12-bit scale
              else
                data <= rx_sh(11 downto 0);
              end if;
              data_valid <= '1';
              div_cnt    <= 0;
              state      <= IDLE;
            else
              div_cnt <= div_cnt + 1;
            end if;
        end case;

        if start = '1' and state /= IDLE then
          miss <= '1';
          -- simulation only: conversion longer than 1/Fs -> samples lost
          assert false report "mcp3202_reader: start while busy (Fs too high for SCLK_HZ)"
            severity error;
        end if;
      end if;
    end if;
  end process;

  busy <= '0' when state = IDLE else '1';
end architecture;
