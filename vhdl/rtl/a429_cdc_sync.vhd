--------------------------------------------------------------------------------
-- Dosya       : a429_cdc_sync.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   Asenkron ARINC 429 alıcı çıkışlarını (ROUTA / ROUTB) metastabiliteye karşı
--   koruyarak IP saat domain'ine senkronlayan çok kademeli FF zinciri.
--
-- Gereksinimler:
--   REQ-1 : G_STAGES >= 2 olmalıdır (derleme/simülasyon anında assert kontrolü).
--           Varsayılan 4 kademe ile yüksek MTBF sağlanır.
--   REQ-2 : Her bit bağımsız G_STAGES kademeli FF zincirinden geçer; toplam
--           sabit yayılım gecikmesi tam G_STAGES clock'tur.
--   REQ-3 : Asenkron rst_n = '0' anında tüm kademeler G_RST_VALUE (ARINC NULL
--           için '0') değerine sıfırlanır.
--   REQ-4 : Sentez araçlarının FF'leri yakın yerleştirmesi için sync_ff üzerine
--           ASYNC_REG = "TRUE" özniteliği uygulanır.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;

entity a429_cdc_sync is
    generic (
        G_STAGES    : positive  := 4;      -- FF kademe sayısı (>= 2)
        G_WIDTH     : positive  := 2;      -- senkronlanacak bit sayısı
        G_RST_VALUE : std_logic := '0'     -- reset değeri (NULL = 0)
    );
    port (
        clk      : in  std_logic;
        rst_n    : in  std_logic;
        async_in : in  std_logic_vector(G_WIDTH - 1 downto 0);
        sync_out : out std_logic_vector(G_WIDTH - 1 downto 0)
    );
end entity a429_cdc_sync;

architecture rtl of a429_cdc_sync is

    type t_sync_chain is array (0 to G_STAGES - 1) of std_logic_vector(G_WIDTH - 1 downto 0);
    signal sync_ff : t_sync_chain;

    -- Xilinx: senkronizasyon FF'lerini yan yana yerleştir, metastabilite analizi yap
    attribute ASYNC_REG : string;
    attribute ASYNC_REG of sync_ff : signal is "TRUE";

begin

    assert G_STAGES >= 2
        report "a429_cdc_sync: G_STAGES en az 2 olmalı" severity failure;

    process (clk, rst_n)
    begin
        if rst_n = '0' then
            sync_ff <= (others => (others => G_RST_VALUE));
        elsif rising_edge(clk) then
            sync_ff(0) <= async_in;
            for i in 1 to G_STAGES - 1 loop
                sync_ff(i) <= sync_ff(i - 1);
            end loop;
        end if;
    end process;

    sync_out <= sync_ff(G_STAGES - 1);

end architecture rtl;
