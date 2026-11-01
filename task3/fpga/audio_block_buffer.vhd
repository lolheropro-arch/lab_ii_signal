-- =============================================================================
-- audio_block_buffer.vhd
-- Task 3 : Ping-pong (double) sample buffer in Block RAM + bank arbitration
--
--   RAM : 2 banks x N words x 12 bit, simple dual-port, inferred as M9K
--         address = bank & index
--   Writer (ADC side) : fills bank 'w_bank' at Fs, never stops.
--   Reader (SPI side) : reads the last COMPLETED bank.
--
-- Handshake with the SPI slave (all signals in the 50 MHz domain):
--   rd_start    : pulse at CS falling edge -> lock the ready bank + snapshot
--                 seq / drop counters (header fields stay consistent).
--   rd_end      : pulse at CS rising edge  -> unlock
--   rd_consumed : level valid with rd_end  -> '1' if the full block was sent,
--                 the bank is then released (blk_ready -> '0').
--
-- Overrun handling (the reader is too slow or the ESP32 is stuck):
--   * Block finished while an older ready block is still unread and NOT being
--     read  -> the newest block replaces it (old one is dropped).
--   * Block finished while the reader is currently reading the other bank
--     -> the just-finished block is discarded (writer re-fills its own bank)
--     so the block being transferred is never overwritten.
--   In both cases drop_cnt increments and 'seq' still advances, so the host
--   sees a gap in the sequence numbers.
-- The ADC write process is NEVER stalled by the reader -> Fs stays constant.
-- =============================================================================
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity audio_block_buffer is
  generic (
    ADDR_W : natural := 10                         -- N = 2**ADDR_W = 1024
  );
  port (
    clk         : in  std_logic;
    rst         : in  std_logic;
    -- sample input (from ADC / test source)
    s_valid     : in  std_logic;
    s_data      : in  std_logic_vector(11 downto 0);
    -- reader control
    rd_start    : in  std_logic;
    rd_end      : in  std_logic;
    rd_consumed : in  std_logic;
    rd_addr     : in  unsigned(ADDR_W - 1 downto 0);
    rd_q        : out std_logic_vector(11 downto 0);  -- 1-clock latency
    -- status
    blk_ready   : out std_logic;                      -- a block waits for the reader
    snap_valid  : out std_logic;                      -- locked block is valid
    snap_seq    : out unsigned(15 downto 0);
    snap_drop   : out unsigned(7 downto 0);
    blk_done    : out std_logic;                      -- pulse each completed block
    overrun     : out std_logic                       -- pulse on each dropped block
  );
end entity;

architecture rtl of audio_block_buffer is
  constant N : natural := 2**ADDR_W;

  type ram_t is array (0 to 2 * N - 1) of std_logic_vector(11 downto 0);
  signal ram : ram_t;

  signal w_bank     : std_logic := '0';
  signal w_idx      : unsigned(ADDR_W - 1 downto 0) := (others => '0');
  signal ready      : std_logic := '0';
  signal ready_bank : std_logic := '0';
  signal ready_seq  : unsigned(15 downto 0) := (others => '0');
  signal seq_cnt    : unsigned(15 downto 0) := (others => '0');
  signal drop_cnt   : unsigned(7 downto 0) := (others => '0');
  signal locked     : std_logic := '0';
  signal lock_bank  : std_logic := '0';

  signal w_addr, r_addr : unsigned(ADDR_W downto 0);
begin
  w_addr <= w_bank & w_idx;
  r_addr <= lock_bank & rd_addr;

  -- --------------------------------------------------------------- Block RAM
  ram_wr : process (clk)
  begin
    if rising_edge(clk) then
      if s_valid = '1' then
        ram(to_integer(w_addr)) <= s_data;
      end if;
    end if;
  end process;

  ram_rd : process (clk)
  begin
    if rising_edge(clk) then
      rd_q <= ram(to_integer(r_addr));
    end if;
  end process;

  -- --------------------------------------------------- bank / handshake logic
  ctrl : process (clk)
    variable reader_busy_other : boolean;
  begin
    if rising_edge(clk) then
      blk_done <= '0';
      overrun  <= '0';
      if rst = '1' then
        w_bank     <= '0';
        w_idx      <= (others => '0');
        ready      <= '0';
        ready_bank <= '0';
        ready_seq  <= (others => '0');
        seq_cnt    <= (others => '0');
        drop_cnt   <= (others => '0');
        locked     <= '0';
        lock_bank  <= '0';
        snap_valid <= '0';
        snap_seq   <= (others => '0');
        snap_drop  <= (others => '0');
      else
        -- ---------------- reader side
        if rd_start = '1' then
          locked     <= ready;
          lock_bank  <= ready_bank;
          snap_valid <= ready;
          snap_seq   <= ready_seq;
          snap_drop  <= drop_cnt;
          if ready = '1' then
            drop_cnt <= (others => '0');
          end if;
        elsif rd_end = '1' then
          locked <= '0';
          if rd_consumed = '1' and locked = '1' and ready_bank = lock_bank then
            ready <= '0';
          end if;
        end if;

        -- ---------------- writer side (never stalls)
        if s_valid = '1' then
          if w_idx = N - 1 then
            w_idx    <= (others => '0');
            seq_cnt  <= seq_cnt + 1;
            blk_done <= '1';

            -- is the reader (already, or just now) holding the other bank?
            reader_busy_other :=
              (locked = '1' and lock_bank /= w_bank) or
              (rd_start = '1' and ready = '1' and ready_bank /= w_bank);

            if reader_busy_other then
              -- discard this block, keep writing into the same bank
              overrun <= '1';
              if drop_cnt /= 255 then drop_cnt <= drop_cnt + 1; end if;
            else
              if ready = '1' and rd_start = '0' then
                -- previous ready block never read -> replaced (dropped)
                overrun <= '1';
                if drop_cnt /= 255 then drop_cnt <= drop_cnt + 1; end if;
              end if;
              ready      <= '1';
              ready_bank <= w_bank;
              ready_seq  <= seq_cnt;
              w_bank     <= not w_bank;
            end if;
          else
            w_idx <= w_idx + 1;
          end if;
        end if;
      end if;
    end if;
  end process;

  blk_ready <= ready and not locked;
end architecture;
