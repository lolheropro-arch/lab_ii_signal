-- =============================================================================
-- tb_audio_system.vhd  --  self-checking testbench for the Task 3 FPGA design
--
--   * behavioural MCP3202 model (returns value = conversion# * 37 mod 4096 and
--     checks the start / SGL / ODD / MSBF bits sent by the FPGA)
--   * ESP32-like SPI master (mode 0, 4 MHz, manual CS) that waits for DRDY,
--     reads full frames and checks SYNC, N, sample continuity and checksum
--   * READ_TEST ramp check and Fs measurement on the fs_tick pin
--
-- Run with GHDL (from task3/fpga):
--   ghdl -a --std=93c sample_tick_gen.vhd mcp3202_reader.vhd test_tone_gen.vhd \
--        audio_block_buffer.vhd spi_slave_block.vhd de10lite_audio_top.vhd \
--        tb/tb_audio_system.vhd
--   ghdl -r --std=93c tb_audio_system --stop-time=200ms
--   (ModelSim/Questa: compile the same files, simulate tb_audio_system)
-- For speed the TB uses N = 64 (ADDR_W = 6) at Fs = 16 kS/s; run with
-- -gADDR_W=10 for the full N = 1024 configuration.
-- =============================================================================
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb_audio_system is
  generic (
    SRC    : natural := 0;          -- 0 = MCP3xxx model, 2 = test tone
    PART   : natural := 3202;       -- 3202 | 3201 | 3204 | 3008
    MSCLK  : natural := 1_000_000;  -- use 800_000 with PART=3201
    ADDR_W : natural := 6;
    FS_HZ  : natural := 16_000;
    NBLK   : natural := 4
  );
end entity;

architecture sim of tb_audio_system is
  constant N        : natural := 2**ADDR_W;
  constant TCLK     : time := 20 ns;                  -- 50 MHz
  constant THALF    : time := 125 ns;                 -- SCLK 4 MHz

  signal clk        : std_logic := '0';
  signal key        : std_logic_vector(1 downto 0) := "11";
  signal sw         : std_logic_vector(9 downto 0) := "0001000000"; -- bin 64
  signal ledr       : std_logic_vector(9 downto 0);
  signal sclk, mosi : std_logic := '0';
  signal cs_n       : std_logic := '1';
  signal miso       : std_logic;
  signal drdy       : std_logic;
  signal fs_tick    : std_logic;
  signal blk_tick   : std_logic;
  signal adc_cs_n, adc_sclk, adc_din : std_logic;
  signal adc_dout   : std_logic := 'Z';

  signal conv_no    : natural := 0;
  signal model_err  : natural := 0;
  signal done       : boolean := false;
  constant nb_tb    : natural := 10 + 2 * boolean'pos(PART /= 3008);
begin
  clk <= not clk after TCLK / 2 when not done else '0';

  dut : entity work.de10lite_audio_top
    generic map (ADC_SELECT => SRC, FS_HZ => FS_HZ, ADDR_W => ADDR_W,
                 MCP_SCLK_HZ => MSCLK, MCP_PART => PART)
    port map (
      MAX10_CLK1_50 => clk, KEY => key, SW => sw, LEDR => ledr,
      spi_sclk => sclk, spi_mosi => mosi, spi_cs_n => cs_n, spi_miso => miso,
      drdy => drdy, fs_tick => fs_tick, blk_tick => blk_tick,
      adc_cs_n => adc_cs_n, adc_sclk => adc_sclk, adc_din => adc_din,
      adc_dout => adc_dout);

  -- ------------------------------------------------------ MCP3202 model
  mcp_model : process
    variable r    : natural;
    variable v    : unsigned(11 downto 0);
    variable din  : std_logic_vector(23 downto 0);
    variable exp  : std_logic_vector(23 downto 0);
    variable nb   : natural;
    variable p    : natural;
  begin
    adc_dout <= 'Z';
    wait until falling_edge(adc_cs_n);
    if PART = 3008 then nb := 10; v := to_unsigned((conv_no * 37) mod 1024, 12);
    else                nb := 12; v := to_unsigned((conv_no * 37) mod 4096, 12); end if;
    exp := (others => '0');                       -- expected DIN, channel 0
    if PART = 3204 then exp(18) := '1'; exp(17) := '1';
    elsif PART = 3008 then exp(16) := '1'; exp(15) := '1';
    else exp(16) := '1'; exp(15) := '1'; exp(13) := '1'; end if;
    conv_no <= conv_no + 1;
    r := 0;
    while adc_cs_n = '0' loop
      wait until rising_edge(adc_sclk) or rising_edge(adc_cs_n);
      exit when adc_cs_n = '1';
      r := r + 1;
      din(24 - r) := adc_din;
      wait until falling_edge(adc_sclk) or rising_edge(adc_cs_n);
      exit when adc_cs_n = '1';
      p := r + 1;                                  -- next bit position
      if PART = 3201 then                          -- Z Z null B11..B0 B1
        if p = 3 then adc_dout <= '0';
        elsif p >= 4 and p <= 15 then adc_dout <= v(15 - p);
        elsif p = 16 then adc_dout <= v(1);
        else adc_dout <= 'Z'; end if;
      elsif p = 24 - nb then adc_dout <= '0';       -- null bit
      elsif p > 24 - nb and p <= 24 then adc_dout <= v(24 - p);
      else adc_dout <= 'Z';
      end if;
    end loop;
    if PART = 3201 then
      if r /= 16 then
        model_err <= model_err + 1;
        report "MCP3201 model: expected 16 clocks, got " & integer'image(r) severity error;
      end if;
    elsif r /= 24 or din(23 downto 12) /= exp(23 downto 12) then
      model_err <= model_err + 1;
      report "MCP3202 model: bad frame r=" & integer'image(r) severity error;
    end if;
  end process;

  -- ---------------------------------------------------- ESP32-like master
  master : process
    type frame_t is array (0 to N + 5) of std_logic_vector(15 downto 0);
    variable fr       : frame_t;
    variable errors   : natural := 0;
    variable sum      : unsigned(15 downto 0);
    variable prev_seq : integer := -1;
    variable seq      : integer;
    variable d        : integer;
    variable t0, t1   : time;

    procedure xfer16 (tx : in std_logic_vector(15 downto 0);
                      rx : out std_logic_vector(15 downto 0)) is
      variable r : std_logic_vector(15 downto 0);
    begin
      for i in 15 downto 0 loop
        mosi <= tx(i);
        wait for THALF;
        sclk <= '1';                               -- master samples MISO here
        r(i) := miso;
        wait for THALF;
        sclk <= '0';
      end loop;
      rx := r;
    end procedure;

    procedure read_frame (cmd : in std_logic_vector(7 downto 0)) is
      variable w : std_logic_vector(15 downto 0);
    begin
      cs_n <= '0';
      wait for 1 us;
      xfer16(cmd & x"00", fr(0));
      for k in 1 to N + 5 loop
        xfer16(x"0000", fr(k));
      end loop;
      wait for 500 ns;
      cs_n <= '1';
      wait for 2 us;
    end procedure;

    procedure check(c : boolean; msg : string) is
    begin
      if not c then
        errors := errors + 1;
        report "CHECK FAILED: " & msg severity error;
      end if;
    end procedure;
  begin
    key <= "10";                                   -- hold reset
    wait for 5 us;
    key <= "11";

    -- ---- Fs measurement on the fs_tick pin (toggles at Fs/2)
    wait until rising_edge(fs_tick);
    t0 := now;
    wait until rising_edge(fs_tick);
    t1 := now;
    report "fs_tick period = " & time'image(t1 - t0) & "  -> Fs = " &
           integer'image(integer(2.0 / (real((t1 - t0) / 1 ns) * 1.0e-9)));
    check(t1 - t0 = 2 * (1 sec / FS_HZ), "Fs mismatch");

    -- ---- status poll before any block: ready must be 0
    cs_n <= '0'; wait for 1 us;
    xfer16(x"0000", fr(0));
    cs_n <= '1'; wait for 2 us;
    check(fr(0)(15 downto 8) = x"C3", "status signature");

    -- ---- normal block reads
    for b in 1 to NBLK loop
      if drdy /= '1' then wait until drdy = '1'; end if;
      wait for 3 us;                               -- ESP32 ISR latency
      read_frame(x"01");
      check(fr(0)(15 downto 8) = x"C3", "status sig");
      check(fr(0)(0) = '1', "status ready bit");
      check(fr(1) = x"A55A", "sync");
      check(unsigned(fr(4)) = N, "N field");
      check(fr(3)(8) = '1', "valid flag");
      check(unsigned(fr(3)(11 downto 10)) = SRC, "source id");
      sum := (others => '0');
      for k in 0 to N - 1 loop
        sum := sum + unsigned(fr(5 + k));
        check(fr(5 + k)(15 downto 12) = "0000", "sample upper nibble");
        if SRC = 0 and k > 0 then
          d := (to_integer(unsigned(fr(5 + k))) - to_integer(unsigned(fr(4 + k)))) mod 4096;
          check(d = 37 * (4096 / (2**nb_tb)), "sample continuity inside block, k=" & integer'image(k));
        end if;
      end loop;
      check(sum = unsigned(fr(N + 5)), "checksum");
      seq := to_integer(unsigned(fr(2)));
      report "block " & integer'image(b) & " seq=" & integer'image(seq) &
             " drop=" & integer'image(to_integer(unsigned(fr(3)(7 downto 0)))) &
             " s[0]=" & integer'image(to_integer(unsigned(fr(5))));
      if prev_seq >= 0 then
        check(seq = prev_seq + 1, "sequence increments by 1 (no drop)");
      end if;
      prev_seq := seq;
      wait for 1 us;
      check(drdy = '0', "drdy cleared after consumed read");
    end loop;

    -- ---- link test (ramp), block must NOT be released
    if drdy /= '1' then wait until drdy = '1'; end if;
    read_frame(x"02");
    check(fr(1) = x"A55A", "sync (test)");
    check(fr(3)(9) = '1', "test flag");
    sum := (others => '0');
    for k in 0 to N - 1 loop
      check(unsigned(fr(5 + k)) = k, "ramp value");
      sum := sum + unsigned(fr(5 + k));
    end loop;
    check(sum = unsigned(fr(N + 5)), "checksum (test)");
    wait for 1 us;
    check(drdy = '1', "drdy still high after READ_TEST");

    -- ---- overrun: stop reading for 3 block periods -> seq gap & drop count
    wait for 3 * N * (1 sec / FS_HZ);
    if drdy /= '1' then wait until drdy = '1'; end if;
    read_frame(x"01");
    seq := to_integer(unsigned(fr(2)));
    report "after pause: seq=" & integer'image(seq) &
           " drop=" & integer'image(to_integer(unsigned(fr(3)(7 downto 0))));
    check(seq > prev_seq + 2, "seq gap after pause");
    check(unsigned(fr(3)(7 downto 0)) > 0, "drop counter after pause");
    check(ledr(2) = '1', "overrun LED");

    if SRC = 0 then
      check(model_err = 0, "MCP3202 command frame");
    end if;

    if errors = 0 then
      report "==== TB PASSED (SRC=" & integer'image(SRC) & ", N=" &
             integer'image(N) & ") ====" severity note;
    else
      report "==== TB FAILED: " & integer'image(errors) & " errors ====" severity failure;
    end if;
    done <= true;
    wait;
  end process;
end architecture;
