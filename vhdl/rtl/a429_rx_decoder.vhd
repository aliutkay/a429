--------------------------------------------------------------------------------
-- a429_rx_decoder
--
-- ARINC 429 alıcı çözücüsü (eski arinc429_rx_fsm). Filtrelenmiş hat durumundan
-- bitleri ölçer, 32 bitlik Word'ü toplar, zaman / gürültü / parity hatalarını bulur.
--
-- Hat durumu (rx_high & rx_low): 00 NULL, 10 HIGH (bit 1), 01 LOW (bit 0), 11 bus fault
--
-- Durumlar:
--   IDLE         : gap ölçülür, bit 0'ın pulse'ı beklenir
--   PULSE        : pulse süresi ölçülür, bit değeri alınır
--   NULL         : bit süresi tamamlanır, sonraki bit beklenir
--   WAIT_GAP     : 32. bitten sonra en az 4 bit NULL beklenir, Word sonra yayınlanır
--
-- Son bitin (bit 31) sonu hattan belli olmadığı için bit 31'in null süresi bit 30'un
-- null süresine eşit kabul edilir: bit 31 sonu = bit 31 pulse + bit 30 null
-- (min_bit ile max_bit arasına sınırlanır). word_gap_dur bu noktadan sonraki NULL'dur;
-- böylece ek Register gerekmeden gerçek gap ölçülür. Bit 31'in bit_null_dur'u da bu tahmindir.
--   ERR_RECOVERY : hatadan sonra (ve reset sonrası) en az 4 bit NULL beklenir
--
-- Word formatı (word_data):
--   [7:0] Label, bit 7 = Label MSB (hatta ilk gönderilen bit), yani Label okunduğu gibi
--   [31:8] hattaki sırasıyla bit 9..32 (SDI, Data, SSM, Parity)
--   TX tarafının word_tx'i aynı formatta olmalıdır (checker bu formatla karşılaştırır).
--
-- Parity (cfg_parity_mode): 00 kontrol yok, 01 Odd, 10 Even, 11 kontrol yok.
--   Parity hatalıysa word_valid ÜRETİLMEZ; sadece err_parity (err_data = Word) üretilir.
--
-- Bir clk'de en fazla bir hata bayrağı üretilir.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity a429_rx_decoder is
    generic (
        G_DUR_W : positive := 16;   -- pulse / null / bit süre sayaçları
        G_GAP_W : positive := 32;   -- gap süre sayacı
        G_CNT_W : positive := 16    -- glitch sayaçları
    );
    port (
        clk                : in  std_logic;
        rst_n              : in  std_logic;
        soft_rst           : in  std_logic := '0';

        -- Config (aktif değerler; decoder IDLE / ERR_RECOVERY'deyken iç kopyaya alınır)
        cfg_min_pulse      : in  std_logic_vector(G_DUR_W - 1 downto 0);
        cfg_max_pulse      : in  std_logic_vector(G_DUR_W - 1 downto 0);
        cfg_min_bit        : in  std_logic_vector(G_DUR_W - 1 downto 0);
        cfg_max_bit        : in  std_logic_vector(G_DUR_W - 1 downto 0);
        cfg_max_pulse_err  : in  std_logic_vector(G_CNT_W - 1 downto 0);
        cfg_max_null_err   : in  std_logic_vector(G_CNT_W - 1 downto 0);
        cfg_max_gap_err    : in  std_logic_vector(G_CNT_W - 1 downto 0);
        cfg_parity_mode    : in  std_logic_vector(1 downto 0);

        -- Glitch filter'dan
        rx_high            : in  std_logic;
        rx_low             : in  std_logic;
        glitch_cnt         : in  std_logic_vector(G_CNT_W - 1 downto 0);  -- glitch_win_cnt

        -- Word çıkışı
        word_start         : out std_logic;   -- bit 0 pulse'ının ilk clk'i (1 clk)
        word_data          : out std_logic_vector(31 downto 0);
        word_gap_dur       : out std_logic_vector(G_GAP_W - 1 downto 0);  -- Word'den önceki gap
        word_gap_err_cnt   : out std_logic_vector(G_CNT_W - 1 downto 0);  -- o gap'teki glitch
        word_valid         : out std_logic;   -- 1 clk; sadece hatasız Word

        -- Bit diagnostic
        bit_idx            : out std_logic_vector(4 downto 0);
        bit_pulse_dur      : out std_logic_vector(G_DUR_W - 1 downto 0);
        bit_null_dur       : out std_logic_vector(G_DUR_W - 1 downto 0);
        bit_pulse_err_cnt  : out std_logic_vector(G_CNT_W - 1 downto 0);
        bit_null_err_cnt   : out std_logic_vector(G_CNT_W - 1 downto 0);
        bit_valid          : out std_logic;   -- 1 clk

        -- Hata bayrakları (1 clk)
        err_bus_fault       : out std_logic;
        err_noise_violation : out std_logic;
        err_gap_violation   : out std_logic;
        err_bit_early       : out std_logic;
        err_pulse_glitch    : out std_logic;
        err_pulse_stuck     : out std_logic;
        err_bit_timeout     : out std_logic;
        err_parity          : out std_logic;
        err_addr            : out std_logic_vector(15 downto 0);  -- bit no, 32 = gap
        err_data            : out std_logic_vector(31 downto 0)   -- süre, glitch sayısı veya Word
    );
end entity a429_rx_decoder;

architecture rtl of a429_rx_decoder is

    type t_state is (ST_IDLE, ST_PULSE, ST_NULL, ST_WAIT_GAP, ST_ERR_RECOVERY);
    signal state : t_state;

    constant C_GAP_MAX  : unsigned(G_GAP_W - 1 downto 0) := (others => '1');
    constant C_ADDR_GAP : std_logic_vector(15 downto 0)  := std_logic_vector(to_unsigned(32, 16));

    -- Sayaçlar
    signal gap_cnt      : unsigned(G_GAP_W - 1 downto 0);
    signal bit_cnt      : unsigned(G_DUR_W - 1 downto 0);
    signal shift_reg    : std_logic_vector(31 downto 0);
    signal parity_acc   : std_logic;
    signal cur_bit      : unsigned(4 downto 0);

    -- Hat durumu
    signal bus_state    : std_logic_vector(1 downto 0);
    signal bus_null     : std_logic;
    signal bus_pulse    : std_logic;
    signal bus_fault    : std_logic;
    signal exp_polarity : std_logic_vector(1 downto 0);

    -- Config iç kopyası
    signal r_min_pulse  : unsigned(G_DUR_W - 1 downto 0);
    signal r_max_pulse  : unsigned(G_DUR_W - 1 downto 0);
    signal r_min_bit    : unsigned(G_DUR_W - 1 downto 0);
    signal r_max_bit    : unsigned(G_DUR_W - 1 downto 0);
    signal r_min_gap_m1 : unsigned(G_DUR_W + 1 downto 0);   -- 4 × min_bit − 1
    signal r_max_p_err  : unsigned(G_CNT_W - 1 downto 0);
    signal r_max_n_err  : unsigned(G_CNT_W - 1 downto 0);
    signal r_max_g_err  : unsigned(G_CNT_W - 1 downto 0);
    signal r_parity     : std_logic_vector(1 downto 0);

    -- Ölçüm kopyaları
    signal cur_pulse_dur : unsigned(G_DUR_W - 1 downto 0);
    signal cur_pulse_err : unsigned(G_CNT_W - 1 downto 0);
    signal cur_null_err  : unsigned(G_CNT_W - 1 downto 0);
    signal prev_null_dur : unsigned(G_DUR_W - 1 downto 0);   -- son tamamlanan bitin null süresi
    signal null_err_base : unsigned(G_CNT_W - 1 downto 0);
    signal lat_gap_dur   : unsigned(G_GAP_W - 1 downto 0);
    signal lat_gap_err   : unsigned(G_CNT_W - 1 downto 0);

    -- Hattaki sıradan Word formatına: Label bitleri (ilk 8 bit) ters çevrilir
    function to_word(sr : std_logic_vector(31 downto 0)) return std_logic_vector is
        variable w : std_logic_vector(31 downto 0);
    begin
        w(31 downto 8) := sr(31 downto 8);
        for i in 0 to 7 loop
            w(i) := sr(7 - i);
        end loop;
        return w;
    end function;

    function gap_ge(g : unsigned; th : unsigned) return boolean is
    begin
        if g'length > th'length then
            return g >= resize(th, g'length);
        else
            return resize(g, th'length) >= th;
        end if;
    end function;

begin

    bus_state <= rx_high & rx_low;
    bus_null  <= '1' when bus_state = "00" else '0';
    bus_pulse <= '1' when bus_state = "10" or bus_state = "01" else '0';
    bus_fault <= '1' when bus_state = "11" else '0';

    process (clk, rst_n)
        variable v_glitch   : unsigned(G_CNT_W - 1 downto 0);
        variable v_bit_done : boolean;
        variable v_par_ok   : boolean;
        variable v_word     : std_logic_vector(31 downto 0);
        variable v_est      : unsigned(G_DUR_W downto 0);   -- bit 31 tahmini bit süresi
        variable v_end      : unsigned(G_DUR_W downto 0);   -- bit 31 bitiş noktası

        -- Hata sonrası ERR_RECOVERY'ye geçiş (sayaçları temizle)
        procedure go_recovery is
        begin
            gap_cnt       <= (others => '0');
            cur_bit       <= (others => '0');
            null_err_base <= (others => '0');
            cur_null_err  <= (others => '0');
            state         <= ST_ERR_RECOVERY;
        end procedure;

        procedure raise(signal flag : out std_logic;
                        addr : in std_logic_vector(15 downto 0);
                        data : in std_logic_vector(31 downto 0)) is
        begin
            flag     <= '1';
            err_addr <= addr;
            err_data <= data;
        end procedure;

        function bit_addr(b : unsigned(4 downto 0)) return std_logic_vector is
        begin
            return std_logic_vector(resize(b, 16));
        end function;

        function dur32(d : unsigned) return std_logic_vector is
        begin
            return std_logic_vector(resize(d, 32));
        end function;
    begin
        if rst_n = '0' then
            state         <= ST_ERR_RECOVERY;
            gap_cnt       <= (others => '0');
            bit_cnt       <= (others => '0');
            shift_reg     <= (others => '0');
            parity_acc    <= '0';
            cur_bit       <= (others => '0');
            exp_polarity  <= "00";

            r_min_pulse   <= to_unsigned(1, G_DUR_W);
            r_max_pulse   <= to_unsigned(1, G_DUR_W);
            r_min_bit     <= to_unsigned(2, G_DUR_W);
            r_max_bit     <= to_unsigned(2, G_DUR_W);
            r_min_gap_m1  <= to_unsigned(7, G_DUR_W + 2);
            r_max_p_err   <= (others => '1');
            r_max_n_err   <= (others => '1');
            r_max_g_err   <= (others => '1');
            r_parity      <= "01";

            cur_pulse_dur <= (others => '0');
            cur_pulse_err <= (others => '0');
            cur_null_err  <= (others => '0');
            prev_null_dur <= (others => '0');
            null_err_base <= (others => '0');
            lat_gap_dur   <= (others => '0');
            lat_gap_err   <= (others => '0');

            word_start        <= '0';
            word_data         <= (others => '0');
            word_gap_dur      <= (others => '0');
            word_gap_err_cnt  <= (others => '0');
            word_valid        <= '0';
            bit_idx           <= (others => '0');
            bit_pulse_dur     <= (others => '0');
            bit_null_dur      <= (others => '0');
            bit_pulse_err_cnt <= (others => '0');
            bit_null_err_cnt  <= (others => '0');
            bit_valid         <= '0';
            err_bus_fault       <= '0';
            err_noise_violation <= '0';
            err_gap_violation   <= '0';
            err_bit_early       <= '0';
            err_pulse_glitch    <= '0';
            err_pulse_stuck     <= '0';
            err_bit_timeout     <= '0';
            err_parity          <= '0';
            err_addr            <= (others => '0');
            err_data            <= (others => '0');

        elsif rising_edge(clk) then
            -- 1 clk'lik çıkışların varsayılanı
            word_start          <= '0';
            word_valid          <= '0';
            bit_valid           <= '0';
            err_bus_fault       <= '0';
            err_noise_violation <= '0';
            err_gap_violation   <= '0';
            err_bit_early       <= '0';
            err_pulse_glitch    <= '0';
            err_pulse_stuck     <= '0';
            err_bit_timeout     <= '0';
            err_parity          <= '0';
            err_addr            <= (others => '0');
            err_data            <= (others => '0');

            v_glitch := unsigned(glitch_cnt);

            -- Config iç kopyası: sadece Word alınmıyorken güncellenir
            if state = ST_IDLE or state = ST_ERR_RECOVERY then
                if unsigned(cfg_min_pulse) = 0 then
                    r_min_pulse <= to_unsigned(1, G_DUR_W);
                else
                    r_min_pulse <= unsigned(cfg_min_pulse);
                end if;
                r_max_pulse <= unsigned(cfg_max_pulse);
                if unsigned(cfg_min_bit) = 0 then
                    r_min_bit    <= to_unsigned(2, G_DUR_W);
                    r_min_gap_m1 <= to_unsigned(7, G_DUR_W + 2);
                else
                    r_min_bit    <= unsigned(cfg_min_bit);
                    r_min_gap_m1 <= shift_left(resize(unsigned(cfg_min_bit), G_DUR_W + 2), 2) - 1;
                end if;
                r_max_bit   <= unsigned(cfg_max_bit);
                r_max_p_err <= unsigned(cfg_max_pulse_err);
                r_max_n_err <= unsigned(cfg_max_null_err);
                r_max_g_err <= unsigned(cfg_max_gap_err);
                r_parity    <= cfg_parity_mode;
            end if;

            if soft_rst = '1' then
                state         <= ST_ERR_RECOVERY;
                gap_cnt       <= (others => '0');
                bit_cnt       <= (others => '0');
                shift_reg     <= (others => '0');
                parity_acc    <= '0';
                cur_bit       <= (others => '0');
                exp_polarity  <= "00";
                cur_pulse_dur <= (others => '0');
                cur_pulse_err <= (others => '0');
                cur_null_err  <= (others => '0');
                prev_null_dur <= (others => '0');
                null_err_base <= (others => '0');
                lat_gap_dur   <= (others => '0');
                lat_gap_err   <= (others => '0');
            elsif bus_fault = '1' then
                -- 11: her durumda hata (toparlanma sırasında tekrar raporlanmaz)
                if state /= ST_ERR_RECOVERY then
                    if state = ST_IDLE or state = ST_WAIT_GAP then
                        raise(err_bus_fault, C_ADDR_GAP, dur32(gap_cnt));
                    else
                        raise(err_bus_fault, bit_addr(cur_bit), dur32(bit_cnt));
                    end if;
                end if;
                go_recovery;

            else
                case state is

                    ------------------------------------------------------------
                    when ST_IDLE =>
                        if v_glitch > r_max_g_err then
                            raise(err_noise_violation, C_ADDR_GAP, dur32(v_glitch));
                            go_recovery;
                        elsif bus_pulse = '1' then
                            -- Bit 0 başladı
                            word_start    <= '1';
                            lat_gap_dur   <= gap_cnt;
                            lat_gap_err   <= cur_null_err - null_err_base;
                            exp_polarity  <= bus_state;
                            bit_cnt       <= to_unsigned(1, G_DUR_W);
                            cur_pulse_err <= v_glitch;
                            cur_bit       <= (others => '0');
                            shift_reg     <= (others => '0');
                            parity_acc    <= '0';
                            state         <= ST_PULSE;
                        else
                            cur_null_err <= v_glitch;
                            if gap_cnt /= C_GAP_MAX then
                                gap_cnt <= gap_cnt + 1;
                            end if;
                        end if;

                    ------------------------------------------------------------
                    when ST_PULSE =>
                        if v_glitch > r_max_p_err then
                            raise(err_noise_violation, bit_addr(cur_bit), dur32(v_glitch));
                            go_recovery;

                        elsif bus_state = exp_polarity then
                            cur_pulse_err <= v_glitch;
                            if bit_cnt >= r_max_pulse then
                                raise(err_pulse_stuck, bit_addr(cur_bit), dur32(bit_cnt));
                                go_recovery;
                            else
                                bit_cnt <= bit_cnt + 1;
                            end if;

                        elsif bus_null = '1' then
                            if bit_cnt < r_min_pulse then
                                raise(err_pulse_glitch, bit_addr(cur_bit), dur32(bit_cnt));
                                go_recovery;
                                null_err_base <= v_glitch;      -- go_recovery'deki 0'ı ezer
                                cur_null_err  <= v_glitch;
                            else
                                -- Pulse bitti: bit değeri = HIGH ise 1
                                shift_reg     <= exp_polarity(1) & shift_reg(31 downto 1);
                                parity_acc    <= parity_acc xor exp_polarity(1);
                                cur_pulse_dur <= bit_cnt;
                                bit_cnt       <= bit_cnt + 1;
                                cur_null_err  <= v_glitch;
                                state         <= ST_NULL;
                            end if;

                        else
                            -- Pulse sırasında polarite değişti (HIGH <-> LOW)
                            raise(err_pulse_glitch, bit_addr(cur_bit), dur32(bit_cnt));
                            go_recovery;
                        end if;

                    ------------------------------------------------------------
                    when ST_NULL =>
                        v_bit_done := false;
                        -- Bit 31 bitiş noktası: pulse + önceki bitin null'u, [min_bit, max_bit] içinde
                        v_est := resize(cur_pulse_dur, G_DUR_W + 1) + resize(prev_null_dur, G_DUR_W + 1);
                        if v_est > resize(r_max_bit, G_DUR_W + 1) then
                            v_est := resize(r_max_bit, G_DUR_W + 1);
                        end if;
                        v_end := v_est;
                        if v_end < resize(r_min_bit, G_DUR_W + 1) then
                            v_end := resize(r_min_bit, G_DUR_W + 1);
                        end if;
                        if v_glitch > r_max_n_err then
                            raise(err_noise_violation, bit_addr(cur_bit), dur32(v_glitch));
                            go_recovery;

                        elsif bus_null = '1' then
                            if cur_bit = 31 and resize(bit_cnt, G_DUR_W + 1) >= v_end then
                                -- Son bit tamam (tahmini bitiş), gap tahmini bitişten itibaren sayılır
                                v_bit_done    := true;
                                null_err_base <= cur_null_err;
                                cur_null_err  <= v_glitch;
                                gap_cnt       <= resize(resize(bit_cnt, G_DUR_W + 1) - v_est + 1, G_GAP_W);
                                state         <= ST_WAIT_GAP;
                            elsif bit_cnt >= r_max_bit then
                                raise(err_bit_timeout, bit_addr(cur_bit), dur32(bit_cnt));
                                go_recovery;
                                null_err_base <= v_glitch;
                                cur_null_err  <= v_glitch;
                            else
                                cur_null_err <= v_glitch;
                                bit_cnt      <= bit_cnt + 1;
                            end if;

                        elsif bus_pulse = '1' then
                            if bit_cnt < r_min_bit then
                                raise(err_bit_early, bit_addr(cur_bit), dur32(bit_cnt));
                                go_recovery;
                            elsif cur_bit = 31 then
                                -- 32 bit bitti ama gap gelmeden yeni pulse
                                v_bit_done := true;
                                raise(err_gap_violation, C_ADDR_GAP, (others => '0'));
                                go_recovery;
                            else
                                -- Sonraki bit
                                v_bit_done    := true;
                                exp_polarity  <= bus_state;
                                cur_bit       <= cur_bit + 1;
                                bit_cnt       <= to_unsigned(1, G_DUR_W);
                                cur_pulse_err <= v_glitch;
                                state         <= ST_PULSE;
                            end if;
                        end if;

                        if v_bit_done then
                            prev_null_dur     <= bit_cnt - cur_pulse_dur;
                            bit_idx           <= std_logic_vector(cur_bit);
                            bit_pulse_dur     <= std_logic_vector(cur_pulse_dur);
                            bit_pulse_err_cnt <= std_logic_vector(cur_pulse_err);
                            bit_null_dur      <= std_logic_vector(bit_cnt - cur_pulse_dur);
                            bit_null_err_cnt  <= std_logic_vector(cur_null_err);
                            bit_valid         <= '1';
                        end if;

                    ------------------------------------------------------------
                    when ST_WAIT_GAP =>
                        if v_glitch > r_max_g_err then
                            raise(err_noise_violation, C_ADDR_GAP, dur32(v_glitch));
                            go_recovery;

                        elsif bus_pulse = '1' then
                            raise(err_gap_violation, C_ADDR_GAP, dur32(gap_cnt));
                            go_recovery;

                        else
                            cur_null_err <= v_glitch;
                            if gap_cnt /= C_GAP_MAX then
                                gap_cnt <= gap_cnt + 1;
                            end if;

                            if gap_ge(gap_cnt, r_min_gap_m1) then
                                v_word := to_word(shift_reg);
                                case r_parity is
                                    when "01"   => v_par_ok := parity_acc = '1';   -- Odd
                                    when "10"   => v_par_ok := parity_acc = '0';   -- Even
                                    when others => v_par_ok := true;               -- kontrol yok
                                end case;

                                word_data        <= v_word;
                                word_gap_dur     <= std_logic_vector(lat_gap_dur);
                                word_gap_err_cnt <= std_logic_vector(lat_gap_err);
                                if v_par_ok then
                                    word_valid <= '1';
                                else
                                    raise(err_parity, std_logic_vector(to_unsigned(31, 16)), v_word);
                                end if;
                                state <= ST_IDLE;
                            end if;
                        end if;

                    ------------------------------------------------------------
                    when ST_ERR_RECOVERY =>
                        if bus_null = '1' then
                            cur_null_err <= v_glitch;
                            if gap_cnt /= C_GAP_MAX then
                                gap_cnt <= gap_cnt + 1;
                            end if;
                            if gap_ge(gap_cnt, r_min_gap_m1) then
                                state <= ST_IDLE;
                            end if;
                        else
                            gap_cnt       <= (others => '0');
                            null_err_base <= (others => '0');
                            cur_null_err  <= (others => '0');
                        end if;

                end case;
            end if;
        end if;
    end process;

end architecture rtl;
