--------------------------------------------------------------------------------
-- Dosya       : a429_tx_word_builder.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   ARINC 429 alanlarından (Label, SDI, Data, SSM) ve seçilen Parity tipinden
--   (Odd / Even) 32-bitlik ARINC 429 Word'ü kombinasyonel olarak oluşturur.
--   a429_tx_core içindeki MUX 1'in (builder_en = '1') kaynağıdır.
--
-- Gereksinimler:
--   REQ-1 : Çıkış Word yerleşimi DESIGN.md ve a429_rx_decoder ile birebir
--           uyumlu olmalıdır:
--             word_out[7:0]   = Label (bit 7 = Label MSB, hatta ilk çıkan bit)
--             word_out[9:8]   = SDI
--             word_out[28:10] = Data (19 bit)
--             word_out[30:29] = SSM
--             word_out[31]    = Parity biti
--   REQ-2 : parity_type = '1' (Odd) iken 32 bit içindeki toplam '1' sayısı tek,
--           parity_type = '0' (Even) iken toplam '1' sayısı çift olmalıdır.
--   REQ-3 : Tamamen kombinasyoneldir (0 clk gecikme); Word Transmitter gönderim
--           başlangıcında çıkışı yakalar (latch).
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;

entity a429_tx_word_builder is
    port (
        label_val   : in  std_logic_vector(7 downto 0);
        sdi         : in  std_logic_vector(1 downto 0);
        data        : in  std_logic_vector(18 downto 0);
        ssm         : in  std_logic_vector(1 downto 0);
        parity_type : in  std_logic;   -- '1': Odd parity, '0': Even parity
        word_out    : out std_logic_vector(31 downto 0)
    );
end entity a429_tx_word_builder;

architecture rtl of a429_tx_word_builder is
begin

    process (label_val, sdi, data, ssm, parity_type)
        variable w31 : std_logic_vector(30 downto 0);
        variable xor_all : std_logic;
        variable par_bit : std_logic;
    begin
        w31     := ssm & data & sdi & label_val;
        xor_all := '0';
        for i in 0 to 30 loop
            xor_all := xor_all xor w31(i);
        end loop;

        if parity_type = '1' then
            par_bit := not xor_all;   -- Odd: toplam 1 sayısı tek
        else
            par_bit := xor_all;       -- Even: toplam 1 sayısı çift
        end if;

        word_out <= par_bit & w31;
    end process;

end architecture rtl;
