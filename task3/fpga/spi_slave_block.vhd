-- =============================================================================
-- spi_slave_block.vhd
-- Task 3 : SPI slave (FPGA) that streams one audio block to the ESP32 master
--
-- SPI mode 0 (CPOL=0, CPHA=0), MSB first, 16-bit words on the wire (big endian)
-- SCLK, MOSI, CS_N are asynchronous: they are synchronised into the 50 MHz
-- domain (2 flip-flops) and edges are detected there.
--   -> MISO changes ~60 ns AFTER each SCLK rising edge (master has already
--      sampled), i.e. it is stable for almost a full SCLK period before the
--      next rising edge.  Reliable up to ~8 MHz; default ESP32 setting 4 MHz.
--
-- ------------------------------------------------------------------ PROTOCOL
-- One transaction = CS_N low ... CS_N high.  Master sends a command in the
-- first byte, the FPGA answers with a fixed frame of 16-bit words:
--
--   word  | MOSI (master)        | MISO (FPGA)
--   ------+----------------------+---------------------------------------------
--   0     | CMD (byte0), 0x00    | 0xC3 | STATUS   (STATUS bit0 = block ready,
--         |                      |        bits3..1 = 0, bits7..4 = version 1)
--   1     | 0x0000 (don't care)  | 0xA55A          SYNC
--   2     |                      | SEQ             block sequence number
--   3     |                      | FLAGS<<8 | DROP FLAGS: b0 valid, b1 test
--         |                      |                 ramp, b3..2 source id
--   4     |                      | N               samples per block (1024)
--   5..   |                      | sample[0..N-1]  0000 & 12-bit ADC code
--   N+5   |                      | CHECKSUM        sum of the N sample words
--                                                  (mod 65536)
--   Total = N + 6 words = 2060 bytes for N = 1024.
--
--   CMD 0x01 READ_BLOCK : real samples, block is released after the full frame
--   CMD 0x02 READ_TEST  : samples replaced by a ramp 0,1,2..N-1 (link test),
--                         block is NOT released
--   other (e.g. 0x00)   : status poll, master may stop after word 0
-- =============================================================================
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity spi_slave_block is
  generic (
    ADDR_W : natural := 10
  );
  port (
    clk         : in  std_logic;
    rst         : in  std_logic;
    -- SPI pins (async)
    spi_sclk    : in  std_logic;
    spi_mosi    : in  std_logic;
    spi_cs_n    : in  std_logic;
    spi_miso    : out std_logic;
    -- buffer interface
    rd_start    : out std_logic;
    rd_end      : out std_logic;
    rd_consumed : out std_logic;
    rd_addr     : out unsigned(ADDR_W - 1 downto 0);
    rd_q        : in  std_logic_vector(11 downto 0);
    blk_ready   : in  std_logic;
    snap_valid  : in  std_logic;
    snap_seq    : in  unsigned(15 downto 0);
    snap_drop   : in  unsigned(7 downto 0);
    source_id   : in  std_logic_vector(1 downto 0);
    busy        : out std_logic                     -- transaction in progress
  );
end entity;

architecture rtl of spi_slave_block is
  constant N         : natural := 2**ADDR_W;
  constant W_SAMPLE0 : natural := 5;
  constant W_CHKSUM  : natural := N + 5;
  constant W_LAST    : natural := N + 5;

  constant CMD_READ_BLOCK : std_logic_vector(7 downto 0) := x"01";
  constant CMD_READ_TEST  : std_logic_vector(7 downto 0) := x"02";
  constant PROTO_VER      : std_logic_vector(3 downto 0) := x"1";

  signal sclk_q, cs_q, mosi_q : std_logic_vector(2 downto 0) := (others => '0');
  signal sclk_rise, cs_fall, cs_rise : std_logic;

  signal active   : std_logic := '0';
  signal bit_cnt  : natural range 0 to 15 := 0;
  signal word_cnt : natural range 0 to N + 7 := 0;   -- word now on the wire
  signal tx_sh    : std_logic_vector(15 downto 0) := (others => '0');
  signal rx_sh    : std_logic_vector(15 downto 0) := (others => '0');
  signal cmd      : std_logic_vector(7 downto 0) := (others => '0');
  signal chksum   : unsigned(15 downto 0) := (others => '0');
  signal done     : std_logic := '0';
  signal next_w   : std_logic_vector(15 downto 0);
  signal nw       : natural range 0 to N + 8;
  signal flags    : std_logic_vector(7 downto 0);
  signal test_on  : std_logic;
begin
  -- ---------------------------------------------------- synchronisers + edges
  process (clk)
  begin
    if rising_edge(clk) then
      sclk_q <= sclk_q(1 downto 0) & spi_sclk;
      cs_q   <= cs_q(1 downto 0)   & spi_cs_n;
      mosi_q <= mosi_q(1 downto 0) & spi_mosi;
    end if;
  end process;

  sclk_rise <= sclk_q(1) and not sclk_q(2);
  cs_fall   <= cs_q(2) and not cs_q(1);
  cs_rise   <= cs_q(1) and not cs_q(2);

  -- ------------------------------------------------------------ word sources
  test_on <= '1' when cmd = CMD_READ_TEST else '0';
  flags   <= "0000" & source_id & test_on & snap_valid;

  nw <= word_cnt + 1;                                -- index of next word to load

  -- RAM address for the NEXT sample word (BRAM has 1-clock latency, the load
  -- happens >= 16 SCLK periods later, so rd_q is long stable by then)
  rd_addr <= to_unsigned((nw - W_SAMPLE0) mod N, ADDR_W);

  process (nw, snap_seq, flags, snap_drop, rd_q, chksum, test_on)
  begin
    if nw = 1 then
      next_w <= x"A55A";
    elsif nw = 2 then
      next_w <= std_logic_vector(snap_seq);
    elsif nw = 3 then
      next_w <= flags & std_logic_vector(snap_drop);
    elsif nw = 4 then
      next_w <= std_logic_vector(to_unsigned(N, 16));
    elsif nw >= W_SAMPLE0 and nw < W_CHKSUM then
      if test_on = '1' then
        next_w <= std_logic_vector(to_unsigned(nw - W_SAMPLE0, 16));
      else
        next_w <= "0000" & rd_q;
      end if;
    elsif nw = W_CHKSUM then
      next_w <= std_logic_vector(chksum);
    else
      next_w <= (others => '0');
    end if;
  end process;

  -- ----------------------------------------------------------- shift engine
  process (clk)
    variable rx_v : std_logic_vector(15 downto 0);
  begin
    if rising_edge(clk) then
      rd_start    <= '0';
      rd_end      <= '0';
      if rst = '1' then
        rd_consumed <= '0';
        active   <= '0';
        bit_cnt  <= 0;
        word_cnt <= 0;
        done     <= '0';
        cmd      <= (others => '0');
      elsif cs_fall = '1' then
        active   <= '1';
        bit_cnt  <= 0;
        word_cnt <= 0;
        chksum   <= (others => '0');
        done     <= '0';
        cmd      <= (others => '0');
        rd_start <= '1';
        -- word 0 = status, first bit must be on MISO before the 1st SCLK edge
        tx_sh    <= x"C3" & PROTO_VER & "000" & blk_ready;
      elsif cs_rise = '1' then
        if active = '1' then
          rd_end <= '1';
          if done = '1' and cmd = CMD_READ_BLOCK then
            rd_consumed <= '1';
          else
            rd_consumed <= '0';
          end if;
        end if;
        active <= '0';
      elsif active = '1' and sclk_rise = '1' then
        rx_v  := rx_sh(14 downto 0) & mosi_q(1);
        rx_sh <= rx_v;
        if word_cnt = 0 and bit_cnt = 7 then
          cmd <= rx_v(7 downto 0);                    -- first byte = command
        end if;

        if bit_cnt = 15 then
          bit_cnt <= 0;
          if word_cnt = W_LAST then
            done <= '1';
          end if;
          if word_cnt <= W_LAST then
            word_cnt <= word_cnt + 1;
          end if;
          tx_sh <= next_w;
          if nw >= W_SAMPLE0 and nw < W_CHKSUM then
            chksum <= chksum + unsigned(next_w);
          end if;
        else
          bit_cnt <= bit_cnt + 1;
          tx_sh   <= tx_sh(14 downto 0) & '0';
        end if;
      end if;
    end if;
  end process;

  spi_miso <= tx_sh(15) when active = '1' else 'Z';
  busy     <= active;
end architecture;
