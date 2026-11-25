--------------------------------------------------------------------------------
-- a429_cdc_sync
--
-- Asenkron giriş sinyallerini IP clock'una senkronlayan çok kademeli FF zinciri.
-- Her bit bağımsız senkronlanır; çok bitlik sinyallerde bitler arası 1 clk kayma
-- olabilir (ARINC hattında rx_high/rx_low aynı anda değişmediği için sorun değildir,
-- glitch filter 2 biti tek sembol olarak filtreler).
--
-- Gecikme: G_STAGES clk.
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
