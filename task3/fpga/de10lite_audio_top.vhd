-- =============================================================================
-- de10lite_audio_top.vhd
-- Task 3 : Audio sampling on the DE10-Lite (MAX 10) + SPI link to the ESP32
--
--   Mic --> [ADC: MCP3202 | MAX10 ADC | test tone] --> ping-pong BRAM
--        --> SPI slave --> ESP32 (master) --> USB serial --> Python/MATLAB
--
--  ADC_SELECT : 0 = external MCP3202 (SPI ADC, default)
--               1 = MAX 10 on-chip ADC (needs adc_pll + adc_core IP)
--               2 = internal DDS test tone (SW selects frequency)
--
--  Sampling is clocked only by the 50 MHz oscillator (sample_tick_gen). The
--  SPI transfer never stalls the ADC path -> Fs = 16 000 S/s exactly.
--
--  I/O summary (pins in de10lite_pins.tcl):
--    GPIO[0] spi_sclk  in   <- ESP32 GPIO18 (VSPI SCK)
--    GPIO[1] spi_mosi  in   <- ESP32 GPIO23 (VSPI MOSI)
--    GPIO[2] spi_miso  out  -> ESP32 GPIO19 (VSPI MISO)
--    GPIO[3] spi_cs_n  in   <- ESP32 GPIO5  (CS, manual)
--    GPIO[4] drdy      out  -> ESP32 GPIO4  (block ready, active high)
--    GPIO[5] fs_tick   out  -> scope : Fs/2 square wave (8 kHz)
--    GPIO[6] adc_cs_n  out  -> MCP3202 pin 1 (CS/SHDN)
--    GPIO[7] adc_sclk  out  -> MCP3202 pin 7 (CLK)
--    GPIO[8] adc_din   out  -> MCP3202 pin 5 (DIN)
--    GPIO[9] adc_dout  in   <- MCP3202 pin 6 (DOUT)
--    GPIO[10] blk_tick out  -> scope : toggles every completed block (64 ms)
--    KEY0 = reset, KEY1 = test tone half-bin offset, SW = test tone frequency
--    LEDR0 heartbeat, LEDR1 drdy, LEDR2 overrun (sticky), LEDR3 clipping,
--    LEDR9..4 level meter (peak of |x - mid| per block)
-- =============================================================================
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity de10lite_audio_top is
  generic (
    ADC_SELECT  : natural := 0;
    CLK_HZ      : natural := 50_000_000;
    FS_HZ       : natural := 16_000;
    ADDR_W      : natural := 10;           -- N = 1024
    MCP_SCLK_HZ : natural := 1_000_000;
    MCP_CHANNEL : natural := 0;
    MCP_PART    : natural := 3202;          -- 3202 | 3204 | 3208 | 3004 | 3008
    MAX10_CH    : natural := 1             -- Arduino A0
  );
  port (
    MAX10_CLK1_50 : in  std_logic;
    KEY           : in  std_logic_vector(1 downto 0);   -- active low
    SW            : in  std_logic_vector(9 downto 0);
    LEDR          : out std_logic_vector(9 downto 0);
    -- ESP32 SPI link
    spi_sclk      : in  std_logic;
    spi_mosi      : in  std_logic;
    spi_cs_n      : in  std_logic;
    spi_miso      : out std_logic;
    drdy          : out std_logic;
    -- debug / verification outputs
    fs_tick       : out std_logic;
    blk_tick      : out std_logic;
    -- MCP3202
    adc_cs_n      : out std_logic;
    adc_sclk      : out std_logic;
    adc_din       : out std_logic;
    adc_dout      : in  std_logic
  );
end entity;

architecture rtl of de10lite_audio_top is

  component max10_adc_sampler is
    generic (CHANNEL : natural := 1);
    port (
      clk        : in  std_logic;
      rst        : in  std_logic;
      start      : in  std_logic;
      data_valid : out std_logic;
      data       : out std_logic_vector(11 downto 0);
      pll_locked : out std_logic
    );
  end component;

  signal clk        : std_logic;
  signal rst        : std_logic := '1';
  signal por_cnt    : unsigned(15 downto 0) := (others => '0');
  signal key_s      : std_logic_vector(1 downto 0) := (others => '1');
  signal sw_s       : std_logic_vector(9 downto 0) := (others => '0');

  signal tick       : std_logic;
  signal tick_tog   : std_logic;
  signal s_valid    : std_logic := '0';
  signal s_data     : std_logic_vector(11 downto 0) := (others => '0');

  signal rd_start, rd_end, rd_consumed : std_logic;
  signal rd_addr    : unsigned(ADDR_W - 1 downto 0);
  signal rd_q       : std_logic_vector(11 downto 0);
  signal blk_ready  : std_logic;
  signal snap_valid : std_logic;
  signal snap_seq   : unsigned(15 downto 0);
  signal snap_drop  : unsigned(7 downto 0);
  signal blk_done   : std_logic;
  signal overrun    : std_logic;
  signal spi_busy   : std_logic;

  signal ovr_led    : std_logic := '0';
  signal blk_tog    : std_logic := '0';
  signal hb_cnt     : unsigned(13 downto 0) := (others => '0');
  signal hb_led     : std_logic := '0';
  signal peak, peak_show : unsigned(11 downto 0) := (others => '0');
  signal clip_cnt   : unsigned(11 downto 0) := (others => '0');
  signal source_id  : std_logic_vector(1 downto 0);
  signal key1_pressed : std_logic;
begin
  clk       <= MAX10_CLK1_50;
  source_id <= std_logic_vector(to_unsigned(ADC_SELECT, 2));
  key1_pressed <= not key_s(1);

  -- ------------------------------------------- reset (power-on + KEY0) & sync
  process (clk)
  begin
    if rising_edge(clk) then
      key_s <= KEY;
      sw_s  <= SW;
      if key_s(0) = '0' then
        por_cnt <= (others => '0');
        rst     <= '1';
      elsif por_cnt /= x"FFFF" then
        por_cnt <= por_cnt + 1;
        rst     <= '1';
      else
        rst <= '0';
      end if;
    end if;
  end process;

  -- ------------------------------------------------------ hardware Fs tick
  u_tick : entity work.sample_tick_gen
    generic map (CLK_HZ => CLK_HZ, FS_HZ => FS_HZ)
    port map (clk => clk, rst => rst, tick => tick, tick_toggle => tick_tog);

  fs_tick <= tick_tog;

  -- ----------------------------------------------------------- ADC sources
  g_mcp : if ADC_SELECT = 0 generate
    u_adc : entity work.mcp3202_reader
      generic map (CLK_HZ => CLK_HZ, SCLK_HZ => MCP_SCLK_HZ, CHANNEL => MCP_CHANNEL,
                   MCP_PART => MCP_PART)
      port map (
        clk => clk, rst => rst, start => tick, busy => open,
        data_valid => s_valid, data => s_data,
        adc_cs_n => adc_cs_n, adc_sclk => adc_sclk,
        adc_din => adc_din, adc_dout => adc_dout);
  end generate;

  g_max10 : if ADC_SELECT = 1 generate
    u_adc : max10_adc_sampler
      generic map (CHANNEL => MAX10_CH)
      port map (
        clk => clk, rst => rst, start => tick,
        data_valid => s_valid, data => s_data, pll_locked => open);
    adc_cs_n <= '1'; adc_sclk <= '0'; adc_din <= '0';
  end generate;

  g_tone : if ADC_SELECT = 2 generate
    u_adc : entity work.test_tone_gen
      port map (
        clk => clk, rst => rst, start => tick,
        bin_sel  => sw_s(8 downto 0),
        half_bin => key1_pressed,
        two_tone => sw_s(9),
        data_valid => s_valid, data => s_data);
    adc_cs_n <= '1'; adc_sclk <= '0'; adc_din <= '0';
  end generate;

  -- --------------------------------------------------- ping-pong block RAM
  u_buf : entity work.audio_block_buffer
    generic map (ADDR_W => ADDR_W)
    port map (
      clk => clk, rst => rst,
      s_valid => s_valid, s_data => s_data,
      rd_start => rd_start, rd_end => rd_end, rd_consumed => rd_consumed,
      rd_addr => rd_addr, rd_q => rd_q,
      blk_ready => blk_ready, snap_valid => snap_valid,
      snap_seq => snap_seq, snap_drop => snap_drop,
      blk_done => blk_done, overrun => overrun);

  -- ------------------------------------------------------------ SPI slave
  u_spi : entity work.spi_slave_block
    generic map (ADDR_W => ADDR_W)
    port map (
      clk => clk, rst => rst,
      spi_sclk => spi_sclk, spi_mosi => spi_mosi, spi_cs_n => spi_cs_n,
      spi_miso => spi_miso,
      rd_start => rd_start, rd_end => rd_end, rd_consumed => rd_consumed,
      rd_addr => rd_addr, rd_q => rd_q,
      blk_ready => blk_ready, snap_valid => snap_valid,
      snap_seq => snap_seq, snap_drop => snap_drop,
      source_id => source_id, busy => spi_busy);

  drdy <= blk_ready;

  -- ------------------------------------------------ LEDs / debug outputs
  process (clk)
    variable dev : signed(12 downto 0);
    variable mag : unsigned(11 downto 0);
  begin
    if rising_edge(clk) then
      if rst = '1' then
        ovr_led  <= '0';
        blk_tog  <= '0';
        hb_cnt   <= (others => '0');
        hb_led   <= '0';
        peak     <= (others => '0');
        peak_show<= (others => '0');
        clip_cnt <= (others => '0');
      else
        if overrun = '1' then ovr_led <= '1'; end if;   -- cleared by KEY0

        -- heartbeat: toggles every 8192 samples (~0.5 s at 16 kS/s)
        if tick = '1' then
          hb_cnt <= hb_cnt + 1;
          if hb_cnt = 0 then hb_led <= not hb_led; end if;
        end if;

        if s_valid = '1' then
          dev := signed('0' & s_data) - 2048;
          if dev < 0 then mag := unsigned(resize(-dev, 12));
          else            mag := unsigned(resize(dev, 12)); end if;
          if mag > peak then peak <= mag; end if;
          -- clipping: within 8 codes of either rail -> light LED ~0.25 s
          if unsigned(s_data) > 4087 or unsigned(s_data) < 8 then
            clip_cnt <= to_unsigned(4000, 12);
          elsif clip_cnt /= 0 then
            clip_cnt <= clip_cnt - 1;
          end if;
        end if;

        if blk_done = '1' then
          blk_tog   <= not blk_tog;
          peak_show <= peak;
          peak      <= (others => '0');
        end if;
      end if;
    end if;
  end process;

  blk_tick <= blk_tog;

  LEDR(0) <= hb_led;
  LEDR(1) <= blk_ready;
  LEDR(2) <= ovr_led;
  LEDR(3) <= '1' when clip_cnt /= 0 else '0';
  -- 6-step level meter, roughly 6 dB per LED
  LEDR(4) <= '1' when peak_show >= 32   else '0';
  LEDR(5) <= '1' when peak_show >= 64   else '0';
  LEDR(6) <= '1' when peak_show >= 128  else '0';
  LEDR(7) <= '1' when peak_show >= 256  else '0';
  LEDR(8) <= '1' when peak_show >= 512  else '0';
  LEDR(9) <= '1' when peak_show >= 1024 else '0';
end architecture;
