#!/usr/bin/env bash
# Record the five shipped examples, smallest design first, after checking their notes.
#
# The k6 VTR architecture is used when one is around ($VTR_ROOT, else the odin3-ws checkout),
# else the LPM tech library ($ODIN3_ROOT/lib/lpm.o3lib). Paths resolve from this script, so it
# runs from any directory; each trace lands in examples/<name>/trace.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
verdandi=${VERDANDI:-verdandi}

arch=${VTR_ROOT:-$HOME/odin3-ws/external/vtr-verilog-to-routing}/vtr_flow/arch/timing/k6_frac_N10_frac_chain_mem32K_40nm.xml
if [[ -f $arch ]]; then
  source_args=(--arch "$arch")
else
  : "${ODIN3_ROOT:?set ODIN3_ROOT (or VTR_ROOT) to record with the LPM tech library}"
  source_args=(--techlib "$ODIN3_ROOT/lib/lpm.o3lib")
fi

# Directory, top module, source file: the smallest design first, the four-module top last.
examples=(
  "counter counter2 counter/counter.v"
  "register ifelse_reg register/register.v"
  "multiplier mul4 multiplier/multiplier.v"
  "instantiation instantiation_top instantiation/instantiation.v"
  "playthrough playthrough playthrough/playthrough.v"
)

for entry in "${examples[@]}"; do
  read -r name top source <<<"$entry"
  echo "== $name"
  "$verdandi" check-notes --notes "$root/examples/$name/notes"
  "$verdandi" record "$root/examples/$source" --top "$top" \
    "${source_args[@]}" -o "$root/examples/$name/trace"
done
