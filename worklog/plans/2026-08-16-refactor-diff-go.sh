#!/bin/zsh
# Behaviour-preservation harness for engine/rules/bot/rl/review.
# Usage: diff_go.sh <outdir>   then diff two outdirs.
cd "$(git rev-parse --show-toplevel)" || exit 1
OUT=${1:?usage: diff_go.sh <outdir>}
mkdir -p "$OUT"
for s in 1 2 3 7 42 101 999; do
  go run ./cmd/rlpaipu --seed $s --match-id "diff-$s" --output "$OUT/seed-$s.json" >/dev/null || exit 1
done
echo "wrote $(ls "$OUT" | wc -l | tr -d ' ') paipu files to $OUT"
