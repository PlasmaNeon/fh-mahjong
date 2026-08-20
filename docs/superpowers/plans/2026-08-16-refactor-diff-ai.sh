#!/bin/zsh
# Behaviour-preservation harness for the ai serving/eval path (Spec B2c hard gate).
cd "$(git rev-parse --show-toplevel)" || exit 1
uv run --project ai fh-mj-serving-parity \
  --checkpoint ai/checkpoints/deploy/selfplay-deep4-student-iter275-39ch.pt \
  --event-history-window 0 --episodes 4 --start-seed 950000 --in-process \
  --bridge-kind go --bridge-lib build/libfh_mahjong_bridge.dylib
