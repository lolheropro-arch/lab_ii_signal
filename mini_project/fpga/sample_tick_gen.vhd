-- =============================================================================
-- sample_tick_gen.vhd
-- Task 3 : Hardware sample-rate generator (clock-enable, NOT a derived clock)
--
-- Produces a single-cycle 'tick' pulse every CLK_HZ/FS_HZ system clocks.
--   50 MHz / 16 kHz = 3125 clocks  ->  Fs = 16 000.000 S/s exactly
-- 'tick_toggle' flips on every tick, so on a GPIO pin it is a square wave of
-- Fs/2 (8 kHz).  Measure it with the oscilloscope to prove the sampling rate
-- is fixed and is never disturbed by the SPI / USB data transfer.
-- =============================================================================
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sample_tick_gen is
  generic (
    CLK_HZ : natural := 50_000_000;
    FS_HZ  : natural := 16_000
  );
  port (
    clk         : in  std_logic;
    rst         : in  std_logic;   -- synchronous, active high
    tick        : out std_logic;   -- 1-clock pulse at Fs
    tick_toggle : out std_logic    -- Fs/2 square wave for the scope
  );
end entity;

architecture rtl of sample_tick_gen is
  constant DIV : natural := CLK_HZ / FS_HZ;
  signal cnt   : natural range 0 to DIV - 1 := 0;
  signal tog   : std_logic := '0';
begin
  assert (CLK_HZ mod FS_HZ) = 0
    report "CLK_HZ/FS_HZ is not an integer -> actual Fs = CLK_HZ/floor(CLK_HZ/FS_HZ)"
    severity warning;

  process (clk)
  begin
    if rising_edge(clk) then
      tick <= '0';
      if rst = '1' then
        cnt <= 0;
        tog <= '0';
      elsif cnt = DIV - 1 then
        cnt  <= 0;
        tick <= '1';
        tog  <= not tog;
      else
        cnt <= cnt + 1;
      end if;
    end if;
  end process;

  tick_toggle <= tog;
end architecture;
