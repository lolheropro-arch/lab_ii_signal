-- =============================================================================
-- test_tone_gen.vhd
-- Task 3 : internal digital test source (ADC_SELECT = 2)
--
-- Replaces the ADC with a DDS sine generator so the whole chain
-- FPGA buffer -> SPI -> ESP32 -> USB -> host FFT can be verified with an
-- EXACTLY known frequency and with no analog noise.
--
-- Frequency (with Fs = 16 kS/s, N = 1024):
--   phase increment = SW(8 downto 0) * 2^22 (+ 2^21 when KEY1 is held)
--   f = SW * Fs / 1024 = SW * 15.625 Hz      -> exactly on FFT bin #SW
--   KEY1 held                                 -> f is shifted by half a bin
--                                                (worst-case spectral leakage)
--   SW(9) = 1                                 -> add a 2nd tone at bin 192
--                                                (3000 Hz, half amplitude)
-- Output: unsigned 12-bit, mid-scale 2048 (like a mic with DC offset).
-- =============================================================================
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.math_real.all;

entity test_tone_gen is
  port (
    clk        : in  std_logic;
    rst        : in  std_logic;
    start      : in  std_logic;                    -- Fs tick
    bin_sel    : in  std_logic_vector(8 downto 0); -- tone frequency in bins
    half_bin   : in  std_logic;                    -- +0.5 bin offset
    two_tone   : in  std_logic;
    data_valid : out std_logic;
    data       : out std_logic_vector(11 downto 0)
  );
end entity;

architecture rtl of test_tone_gen is
  constant LUT_BITS : natural := 10;               -- 1024-entry sine table
  type lut_t is array (0 to 2**LUT_BITS - 1) of signed(11 downto 0);

  function make_lut return lut_t is
    variable t : lut_t;
  begin
    for i in t'range loop
      -- amplitude +-1000 counts (leaves headroom for the 2nd tone)
      t(i) := to_signed(integer(round(1000.0 * sin(2.0 * MATH_PI * real(i) / real(2**LUT_BITS)))), 12);
    end loop;
    return t;
  end function;

  constant SINE : lut_t := make_lut;

  signal ph1, ph2 : unsigned(31 downto 0) := (others => '0');
  constant INC2   : unsigned(31 downto 0) := to_unsigned(192 * 2**22, 32); -- 3 kHz
begin
  process (clk)
    variable inc1 : unsigned(31 downto 0);
    variable s1   : signed(12 downto 0);
    variable s2   : signed(12 downto 0);
    variable acc  : signed(13 downto 0);
  begin
    if rising_edge(clk) then
      data_valid <= '0';
      if rst = '1' then
        ph1 <= (others => '0');
        ph2 <= (others => '0');
      elsif start = '1' then
        inc1 := shift_left(resize(unsigned(bin_sel), 32), 22);
        if half_bin = '1' then
          inc1 := inc1 + to_unsigned(2**21, 32);
        end if;
        ph1 <= ph1 + inc1;
        ph2 <= ph2 + INC2;

        s1 := resize(SINE(to_integer(ph1(31 downto 32 - LUT_BITS))), 13);
        if two_tone = '1' then
          s2 := shift_right(resize(SINE(to_integer(ph2(31 downto 32 - LUT_BITS))), 13), 1);
        else
          s2 := (others => '0');
        end if;
        acc := resize(s1, 14) + resize(s2, 14) + to_signed(2048, 14);
        data       <= std_logic_vector(acc(11 downto 0));
        data_valid <= '1';
      end if;
    end if;
  end process;
end architecture;
