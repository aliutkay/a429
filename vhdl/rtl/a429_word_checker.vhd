--------------------------------------------------------------------------------
-- a429_word_checker
--
-- TX BIT (wraparound) Word karşılaştırıcısı (DESIGN.md §8.1).
--   * TX gönderime başladığında (tx_word_start) tx_word_tx + ts_now FIFO'ya alınır.
--   * Alıcı geçerli Word aldığında (word_valid) FIFO başıyla karşılaştırılır:
--       eşit   -> chk_ok_cnt +1
--       farklı -> chk_mismatch (data = beklenen Word)
--   * FIFO boşken Word gelirse -> chk_unexpected (data = alınan Word)
--   * Alıcı fiziksel hata verirse (rx_err_any) -> FIFO başı düşürülür
--   * chk_timeout /= 0 ve süre aşılırsa -> chk_no_echo (data = beklenen Word)
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity a429_word_checker is
    generic (
        G_FIFO_DEPTH : positive := 4   -- 2'nin kuvveti (varsayılan 4, en fazla 15)
    );
    port (
        clk            : in  std_logic;
        rst_n          : in  std_logic;
        soft_rst       : in  std_logic;

        chk_en         : in  std_logic;
        chk_clear      : in  std_logic;
        chk_timeout    : in  std_logic_vector(31 downto 0);
        chk_route_ok   : in  std_logic := '1';

        ts_now         : in  std_logic_vector(63 downto 0);

        -- TX tarafı
        tx_word_start  : in  std_logic;
        tx_word_tx     : in  std_logic_vector(31 downto 0);

        -- RX tarafı
        rx_word_data   : in  std_logic_vector(31 downto 0);
        rx_word_valid  : in  std_logic;
        rx_err_any     : in  std_logic;

        -- Logger'a giden hatalar (1 clk darbe)
        chk_mismatch   : out std_logic;
        chk_no_echo    : out std_logic;
        chk_unexpected : out std_logic;
        chk_addr       : out std_logic_vector(15 downto 0);
        chk_data       : out std_logic_vector(31 downto 0);

        -- Durum & sayaçlar
        chk_ok_cnt     : out std_logic_vector(31 downto 0);
        chk_err_cnt    : out std_logic_vector(31 downto 0);
        chk_fifo_level : out std_logic_vector(3 downto 0);
        chk_fifo_ovf   : out std_logic
    );
end entity a429_word_checker;

architecture rtl of a429_word_checker is
    type t_word_arr is array (0 to G_FIFO_DEPTH - 1) of std_logic_vector(31 downto 0);
    type t_ts_arr   is array (0 to G_FIFO_DEPTH - 1) of unsigned(63 downto 0);

    signal fifo_word : t_word_arr;
    signal fifo_ts   : t_ts_arr;
    signal wr_ptr    : natural range 0 to G_FIFO_DEPTH - 1;
    signal rd_ptr    : natural range 0 to G_FIFO_DEPTH - 1;
    signal count     : natural range 0 to G_FIFO_DEPTH;
    signal ovf       : std_logic;

    signal r_ok_cnt  : unsigned(31 downto 0);
    signal r_err_cnt : unsigned(31 downto 0);
begin

    process (clk, rst_n)
        variable v_wr     : natural range 0 to G_FIFO_DEPTH - 1;
        variable v_rd     : natural range 0 to G_FIFO_DEPTH - 1;
        variable v_cnt    : natural range 0 to G_FIFO_DEPTH;
        variable v_active : boolean;
        variable v_exp    : std_logic_vector(31 downto 0);
        variable v_age    : unsigned(63 downto 0);
    begin
        if rst_n = '0' then
            fifo_word      <= (others => (others => '0'));
            fifo_ts        <= (others => (others => '0'));
            wr_ptr         <= 0;
            rd_ptr         <= 0;
            count          <= 0;
            ovf            <= '0';
            r_ok_cnt       <= (others => '0');
            r_err_cnt      <= (others => '0');
            chk_mismatch   <= '0';
            chk_no_echo    <= '0';
            chk_unexpected <= '0';
            chk_addr       <= (others => '0');
            chk_data       <= (others => '0');
        elsif rising_edge(clk) then
            chk_mismatch   <= '0';
            chk_no_echo    <= '0';
            chk_unexpected <= '0';
            chk_addr       <= (others => '0');
            chk_data       <= (others => '0');

            if soft_rst = '1' or chk_clear = '1' then
                wr_ptr <= 0;
                rd_ptr <= 0;
                count  <= 0;
                ovf    <= '0';
                if soft_rst = '1' then
                    r_ok_cnt  <= (others => '0');
                    r_err_cnt <= (others => '0');
                end if;
            else
                v_wr     := wr_ptr;
                v_rd     := rd_ptr;
                v_cnt    := count;
                v_active := (chk_en = '1') and (chk_route_ok = '1');

                if v_active then
                    -- 1) RX / Timeout kontrolü (DESIGN.md: eşzamanlı Word + timeout'ta önce karşılaştırma)
                    if rx_word_valid = '1' then
                        if v_cnt > 0 then
                            v_exp := fifo_word(v_rd);
                            if rx_word_data = v_exp then
                                r_ok_cnt <= r_ok_cnt + 1;
                            else
                                chk_mismatch <= '1';
                                chk_addr     <= std_logic_vector(to_unsigned(v_rd, 16));
                                chk_data     <= v_exp;
                                r_err_cnt    <= r_err_cnt + 1;
                            end if;
                            v_rd  := (v_rd + 1) mod G_FIFO_DEPTH;
                            v_cnt := v_cnt - 1;
                        else
                            chk_unexpected <= '1';
                            chk_addr       <= (others => '0');
                            chk_data       <= rx_word_data;
                            r_err_cnt      <= r_err_cnt + 1;
                        end if;

                    elsif rx_err_any = '1' then
                        -- Alıcı fiziksel hata kaydetti; eşleşen beklenen Word'ü FIFO'dan düşür
                        if v_cnt > 0 then
                            v_rd  := (v_rd + 1) mod G_FIFO_DEPTH;
                            v_cnt := v_cnt - 1;
                        end if;

                    elsif v_cnt > 0 and unsigned(chk_timeout) /= 0 then
                        v_age := unsigned(ts_now) - fifo_ts(v_rd);
                        if v_age >= resize(unsigned(chk_timeout), 64) then
                            chk_no_echo <= '1';
                            chk_addr    <= std_logic_vector(to_unsigned(v_rd, 16));
                            chk_data    <= fifo_word(v_rd);
                            r_err_cnt   <= r_err_cnt + 1;
                            v_rd        := (v_rd + 1) mod G_FIFO_DEPTH;
                            v_cnt       := v_cnt - 1;
                        end if;
                    end if;

                    -- 2) TX yeni Word gönderimi -> FIFO'ya ekle
                    if tx_word_start = '1' then
                        if v_cnt < G_FIFO_DEPTH then
                            fifo_word(v_wr) <= tx_word_tx;
                            fifo_ts(v_wr)   <= unsigned(ts_now);
                            v_wr            := (v_wr + 1) mod G_FIFO_DEPTH;
                            v_cnt           := v_cnt + 1;
                        else
                            ovf <= '1';
                        end if;
                    end if;
                end if;

                wr_ptr <= v_wr;
                rd_ptr <= v_rd;
                count  <= v_cnt;
            end if;
        end if;
    end process;

    chk_ok_cnt     <= std_logic_vector(r_ok_cnt);
    chk_err_cnt    <= std_logic_vector(r_err_cnt);
    chk_fifo_level <= std_logic_vector(to_unsigned(count, 4));
    chk_fifo_ovf   <= ovf;

end architecture rtl;
