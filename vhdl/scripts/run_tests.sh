#!/usr/bin/env bash
# Tüm ARINC 429 VHDL birim/entegrasyon testlerini hem VHDL-93 hem VHDL-2008 ile,
# ayrıca AXIL Studio easyaxil AXI4-Lite testbench'ini ve HDL Designer paketli
# arinc429_ip top entegrasyon testini (ghdl --synth + Icarus Verilog) çalıştırır.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

RTL_FILES=(
  vhdl/rtl/a429_pkg.vhd
  vhdl/rtl/a429_presets_pkg.vhd
  vhdl/rtl/a429_rst_sync.vhd
  vhdl/rtl/a429_timestamp.vhd
  vhdl/rtl/a429_sdp_ram.vhd
  vhdl/rtl/a429_cdc_sync.vhd
  vhdl/rtl/a429_glitch_filter.vhd
  vhdl/rtl/a429_rx_decoder.vhd
  vhdl/rtl/a429_rx_core.vhd
  vhdl/rtl/a429_rx_cfg_sel.vhd
  vhdl/rtl/a429_rx_logger.vhd
  vhdl/rtl/a429_word_checker.vhd
  vhdl/rtl/a429_rx_channel.vhd
  vhdl/rtl/a429_tx_cfg_sel.vhd
  vhdl/rtl/a429_tx_word_builder.vhd
  vhdl/rtl/a429_tx_scheduler.vhd
  vhdl/rtl/a429_tx_transmitter.vhd
  vhdl/rtl/a429_tx_core.vhd
  vhdl/rtl/a429_tx_word_evt.vhd
  vhdl/rtl/a429_tx_channel.vhd
  vhdl/rtl/arinc429_core.vhd
  vhdl/rtl/arinc429_ip.vhd
)

TBS=(
  tb_a429_rst_sync
  tb_a429_timestamp
  tb_a429_sdp_ram
  tb_a429_cdc_sync
  tb_a429_glitch_filter
  tb_a429_rx_decoder
  tb_a429_rx_core
  tb_a429_rx_cfg_sel
  tb_a429_rx_logger
  tb_a429_word_checker
  tb_a429_rx_channel
  tb_a429_tx_cfg_sel
  tb_a429_tx_word_builder
  tb_a429_tx_scheduler
  tb_a429_tx_transmitter
  tb_a429_tx_core
  tb_a429_tx_word_evt
  tb_a429_tx_channel
  tb_arinc429_core
  tb_a429_timing
)

run_vhdl_suite() {
  local std="$1"
  shift
  local work="/tmp/a429_ghdl_${std}"
  rm -rf "$work"
  mkdir -p "$work"
  echo "============================================================"
  echo " VHDL-${std} (${#RTL_FILES[@]} RTL + ${#TBS[@]} unit/integration TB)"
  echo "============================================================"
  ghdl -a --std="$std" "$@" --workdir="$work" "${RTL_FILES[@]}"
  for tb in "${TBS[@]}"; do
    ghdl -a --std="$std" "$@" --workdir="$work" "vhdl/tb/${tb}.vhd"
    out="$(
      cd "$work"
      ghdl -e --std="$std" "$@" "$tb" 2>/dev/null || ghdl -e --std="$std" "$@" "$tb"
      ghdl -r --std="$std" "$@" "$tb" --assert-level=error 2>&1
    )"
    printf "%s\n" "$out" | grep -E "PASS:|SONUC:"
  done
  echo "VHDL-${std}: ${#TBS[@]}/${#TBS[@]} testbench PASSED."
}

run_vhdl_suite 93 -C
run_vhdl_suite 08

echo "============================================================"
echo " Icarus Verilog (AXIL Studio arinc429_axil_tb.v)"
echo "============================================================"
iverilog -g2005 -o /tmp/arinc429_axil_tb.vvp vhdl/axil/arinc429_axil.v vhdl/axil/arinc429_axil_tb.v
vvp /tmp/arinc429_axil_tb.vvp

echo "============================================================"
echo " arinc429_ip top (HDL Designer arinc429_axil_pk) entegrasyon testi"
echo "============================================================"
ghdl --synth --std=08 --workdir=/tmp/a429_ghdl_08 --out=verilog arinc429_ip > /tmp/arinc429_ip_syn.v 2>/dev/null
iverilog -g2012 -o /tmp/tb_arinc429_ip_pk.vvp /tmp/arinc429_ip_syn.v \
  vhdl/axil/arinc429_axil_pk.v vhdl/axil/arinc429_axil.v vhdl/tb/tb_arinc429_ip_pk.v
out="$(vvp /tmp/tb_arinc429_ip_pk.vvp)"
printf "%s\n" "$out"
printf "%s\n" "$out" | grep -q "^PASS:"

echo "============================================================"
echo " arinc429_ip TX -> RX0 loopback (ENABLE, gruplanmis register'lar, hat teshisi)"
echo "============================================================"
iverilog -g2012 -o /tmp/tb_arinc429_ip_loopback.vvp /tmp/arinc429_ip_syn.v \
  vhdl/axil/arinc429_axil_pk.v vhdl/axil/arinc429_axil.v vhdl/tb/tb_arinc429_ip_loopback.v
out="$(vvp /tmp/tb_arinc429_ip_loopback.vvp)"
printf "%s\n" "$out"
printf "%s\n" "$out" | grep -q "^PASS:"
