-- =============================================================================
-- max10_adc_sampler.vhd
-- Task 3 (option A) : MAX 10 on-chip ADC (Modular ADC Core, "control core only")
--
-- Required IP (generate with Quartus IP Catalog -- see README section 3):
--   1) ALTPLL named  "adc_pll"  : inclk0 = 50 MHz, c0 = 10 MHz, 'locked' output
--   2) Modular ADC core named "adc_core" :
--        Core Variant  = "ADC control core only"
--        ADC clock     = 10 MHz (from adc_pll c0)
--        Reference     = Internal 2.5 V
--        Channel 1 (ADC_IN1 = DE10-Lite Arduino header A0) enabled
--      Exported ports (default names when generated from the IP Catalog):
--        clock_clk, reset_sink_reset_n, adc_pll_clock_clk, adc_pll_locked_export,
--        command_valid/channel/startofpacket/endofpacket/ready,
--        response_valid/channel/data/startofpacket/endofpacket
--      If your generated names differ, edit ONLY the component declaration +
--      port map below.
--
-- Operation : one Avalon-ST command (single conversion on CHANNEL) is issued on
-- every Fs tick.  The conversion instant is set by the hardware tick, the
-- 12-bit result arrives a few microseconds later on the response interface.
--
-- DE10-Lite mapping : Arduino A0..A5 -> ADC1 channel 1..6
--   (channel 0 is the dedicated ANAIN1 pin, not on the Arduino header)
-- Voltage : header pins accept 0..5 V, divided to 0..2.5 V internally, so
--   code = Vin / 5.0 V * 4096.  A mic module powered at 3.3 V only uses ~66 %
--   of the range (consider powering the mic at 5 V or using the MCP3202).
-- =============================================================================
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity max10_adc_sampler is
  generic (
    CHANNEL : natural range 0 to 16 := 1          -- 1 = Arduino A0
  );
  port (
    clk        : in  std_logic;                   -- 50 MHz system clock
    rst        : in  std_logic;
    start      : in  std_logic;                   -- Fs tick
    data_valid : out std_logic;
    data       : out std_logic_vector(11 downto 0);
    pll_locked : out std_logic
  );
end entity;

architecture rtl of max10_adc_sampler is

  component adc_pll is
    port (
      inclk0 : in  std_logic;
      c0     : out std_logic;
      locked : out std_logic
    );
  end component;

  component adc_core is
    port (
      adc_pll_clock_clk      : in  std_logic;
      adc_pll_locked_export  : in  std_logic;
      clock_clk              : in  std_logic;
      command_valid          : in  std_logic;
      command_channel        : in  std_logic_vector(4 downto 0);
      command_startofpacket  : in  std_logic;
      command_endofpacket    : in  std_logic;
      command_ready          : out std_logic;
      reset_sink_reset_n     : in  std_logic;
      response_valid         : out std_logic;
      response_channel       : out std_logic_vector(4 downto 0);
      response_data          : out std_logic_vector(11 downto 0);
      response_startofpacket : out std_logic;
      response_endofpacket   : out std_logic
    );
  end component;

  signal clk10    : std_logic;
  signal locked   : std_logic;
  signal rst_n    : std_logic;
  signal cmd_vld  : std_logic := '0';
  signal cmd_rdy  : std_logic;
  signal rsp_vld  : std_logic;
  signal rsp_data : std_logic_vector(11 downto 0);
  signal rsp_ch   : std_logic_vector(4 downto 0);
begin
  u_pll : adc_pll
    port map (inclk0 => clk, c0 => clk10, locked => locked);

  rst_n <= not rst;

  u_adc : adc_core
    port map (
      adc_pll_clock_clk      => clk10,
      adc_pll_locked_export  => locked,
      clock_clk              => clk,
      command_valid          => cmd_vld,
      command_channel        => std_logic_vector(to_unsigned(CHANNEL, 5)),
      command_startofpacket  => '1',
      command_endofpacket    => '1',
      command_ready          => cmd_rdy,
      reset_sink_reset_n     => rst_n,
      response_valid         => rsp_vld,
      response_channel       => rsp_ch,
      response_data          => rsp_data,
      response_startofpacket => open,
      response_endofpacket   => open
    );

  -- Avalon-ST command handshake: hold command_valid until command_ready.
  process (clk)
  begin
    if rising_edge(clk) then
      data_valid <= '0';
      if rst = '1' or locked = '0' then
        cmd_vld <= '0';
      else
        if start = '1' then
          cmd_vld <= '1';
        elsif cmd_vld = '1' and cmd_rdy = '1' then
          cmd_vld <= '0';
        end if;

        if rsp_vld = '1' then
          data       <= rsp_data;
          data_valid <= '1';
        end if;
      end if;
    end if;
  end process;

  pll_locked <= locked;
end architecture;
