--------------------------------------------------------------------------------
-- tb_a429_tx_word_builder — a429_tx_word_builder birim testi (VHDL-93 / 2008)
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;

entity tb_a429_tx_word_builder is
end entity tb_a429_tx_word_builder;

architecture sim of tb_a429_tx_word_builder is
    signal label_val   : std_logic_vector(7 downto 0)  := (others => '0');
    signal sdi         : std_logic_vector(1 downto 0)  := (others => '0');
    signal data        : std_logic_vector(18 downto 0) := (others => '0');
    signal ssm         : std_logic_vector(1 downto 0)  := (others => '0');
    signal parity_type : std_logic := '1';
    signal word_out    : std_logic_vector(31 downto 0);
    signal errors      : natural := 0;

    function popcount(v : std_logic_vector) return natural is
        variable c : natural := 0;
    begin
        for i in v'range loop
            if v(i) = '1' then c := c + 1; end if;
        end loop;
        return c;
    end function;
begin
    dut : entity work.a429_tx_word_builder
        port map (
            label_val => label_val, sdi => sdi, data => data, ssm => ssm,
            parity_type => parity_type, word_out => word_out
        );

    process
        procedure chk(cond : boolean; msg : string) is
        begin
            if not cond then report "HATA: " & msg severity error; errors <= errors + 1; end if;
        end procedure;
    begin
        -- 1) Tümü sıfır + Odd -> bit 31 = '1' (toplam 1 sayısı = 1)
        label_val <= x"00"; sdi <= "00"; data <= (others => '0'); ssm <= "00"; parity_type <= '1';
        wait for 5 ns;
        chk(word_out = x"80000000" and (popcount(word_out) mod 2 = 1), "Sifir + Odd parity=1 olmali");

        -- 2) Tümü sıfır + Even -> bit 31 = '0' (toplam 1 sayısı = 0)
        parity_type <= '0';
        wait for 5 ns;
        chk(word_out = x"00000000" and (popcount(word_out) mod 2 = 0), "Sifir + Even parity=0 olmali");

        -- 3) Label=0o310 (0xC8), SDI=1, Data=0x12345, SSM=3 + Odd
        label_val <= x"C8"; sdi <= "01"; data <= "001" & x"2345"; ssm <= "11"; parity_type <= '1';
        wait for 5 ns;
        chk(word_out(7 downto 0) = x"C8" and word_out(9 downto 8) = "01"
            and word_out(28 downto 10) = ("001" & x"2345") and word_out(30 downto 29) = "11",
            "Word alan yerlesimi dogru olmali");
        chk((popcount(word_out) mod 2) = 1, "Odd parity toplam 1 sayisi tek olmali");

        -- 4) Aynı alanlar + Even
        parity_type <= '0';
        wait for 5 ns;
        chk((popcount(word_out) mod 2) = 0, "Even parity toplam 1 sayisi cift olmali");

        -- 5) Tümü 1 (31 tane 1 = tek) -> Odd parity='0', Even parity='1'
        label_val <= x"FF"; sdi <= "11"; data <= (others => '1'); ssm <= "11"; parity_type <= '1';
        wait for 5 ns;
        chk(word_out = x"7FFFFFFF", "31 adet 1 + Odd -> bit31=0");
        parity_type <= '0';
        wait for 5 ns;
        chk(word_out = x"FFFFFFFF", "31 adet 1 + Even -> bit31=1");

        if errors = 0 then
            report "PASS: tb_a429_tx_word_builder" severity note;
        else
            report "FAIL: tb_a429_tx_word_builder (" & integer'image(errors) & " hata)" severity failure;
        end if;
        wait;
    end process;
end architecture sim;
