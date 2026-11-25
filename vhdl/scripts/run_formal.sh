#!/usr/bin/env bash
# GHDL synth (VHDL -> Verilog) + Yosys SAT Formal Doğrulama Koşucusu
#   * Kombinasyonel tam ispat (tüm 2^32 giriş uzayı)
#   * k-İndüksiyon (tüm t >= 0 için sonsuz zaman ispatı)
#   * Bounded Model Checking (BMC, derinlik N)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

WORK="/tmp/a429_formal"
rm -rf "$WORK"
mkdir -p "$WORK"

prove_comb() {
  local name="$1"
  local ent="$2"
  shift 2
  echo ">>> [COMB] ${name} ..."
  ghdl synth --std=08 --out=verilog "$@" -e "$ent" > "${WORK}/${ent}.v" 2>/dev/null
  yosys -q -p "
    read_verilog -sv -formal ${WORK}/${ent}.v vhdl/formal/${name}.sv;
    prep -top ${name};
    flatten;
    chformal -lower;
    opt -fast;
    sat -verify -prove-asserts -show-ports
  "
  echo "    PROVEN (tüm kombinasyonlar): ${name}"
}

prove_seq() {
  local name="$1"
  local mode="$2"     # induct | bmc
  local depth="$3"
  local ent="$4"
  shift 4
  echo ">>> [${mode} d=${depth}] ${name} ..."
  if [ "$ent" != "VERILOG_DIRECT" ]; then
    ghdl synth --std=08 --out=verilog "$@" -e "$ent" > "${WORK}/${ent}.v" 2>/dev/null
    local dut_v="${WORK}/${ent}.v"
  else
    local dut_v="$1"
  fi

  local sat_cmd
  if [ "$mode" = "induct" ]; then
    sat_cmd="sat -verify -prove-asserts -tempinduct -maxsteps ${depth} -set-init-zero -seq 1"
  else
    sat_cmd="sat -verify -prove-asserts -tempinduct-baseonly -maxsteps ${depth} -set-init-zero"
  fi

  yosys -q -p "
    read_verilog ${dut_v};
    read_verilog -sv -formal vhdl/formal/${name}.sv;
    prep -top ${name};
    flatten;
    async2sync;
    chformal -lower;
    opt -fast;
    ${sat_cmd}
  "
  echo "    PROVEN (${mode}, depth=${depth}): ${name}"
}

echo "============================================================"
echo " ARINC 429 Formal Doğrulama (GHDL synth + Yosys SAT)"
echo "============================================================"

# 1. Kombinasyonel 2^32 tam ispat
prove_comb fv_a429_tx_word_builder a429_tx_word_builder vhdl/rtl/a429_tx_word_builder.vhd

# 2. k-İndüksiyon (sonsuz zaman ispatları)
prove_seq fv_a429_tx_word_evt  induct 10 a429_tx_word_evt  vhdl/rtl/a429_tx_word_evt.vhd
prove_seq fv_a429_tx_scheduler induct 10 a429_tx_scheduler vhdl/rtl/a429_tx_scheduler.vhd
prove_seq fv_a429_timestamp    induct 10 a429_timestamp    vhdl/rtl/a429_timestamp.vhd
prove_seq fv_a429_rx_cfg_sel   induct 10 a429_rx_cfg_sel   vhdl/rtl/a429_pkg.vhd vhdl/rtl/a429_presets_pkg.vhd vhdl/rtl/a429_rx_cfg_sel.vhd
prove_seq fv_a429_tx_cfg_sel   induct 10 a429_tx_cfg_sel   vhdl/rtl/a429_pkg.vhd vhdl/rtl/a429_presets_pkg.vhd vhdl/rtl/a429_tx_cfg_sel.vhd
prove_seq fv_a429_rx_logger    induct 10 a429_rx_logger    vhdl/rtl/a429_pkg.vhd vhdl/rtl/a429_rx_logger.vhd

# 3. Bounded Model Checking (BMC — karmaşık FSM / FIFO / AXI4-Lite blokları)
prove_seq fv_a429_glitch_filter  bmc 14 a429_glitch_filter  vhdl/rtl/a429_glitch_filter.vhd
prove_seq fv_a429_tx_transmitter bmc 14 a429_tx_transmitter vhdl/rtl/a429_pkg.vhd vhdl/rtl/a429_tx_transmitter.vhd
prove_seq fv_a429_tx_core        bmc 12 a429_tx_core        vhdl/rtl/a429_pkg.vhd vhdl/rtl/a429_tx_word_builder.vhd vhdl/rtl/a429_tx_scheduler.vhd vhdl/rtl/a429_tx_transmitter.vhd vhdl/rtl/a429_tx_core.vhd
prove_seq fv_a429_rx_decoder     bmc 12 a429_rx_decoder     vhdl/rtl/a429_rx_decoder.vhd
prove_seq fv_a429_word_checker   bmc 12 a429_word_checker   vhdl/rtl/a429_word_checker.vhd
prove_seq fv_arinc429_axil       bmc 10 VERILOG_DIRECT      vhdl/axil/arinc429_axil.v

echo "============================================================"
echo " TUM 13 FORMAL ISPAT BASARIYLA TAMAMLANDI!"
echo "============================================================"
