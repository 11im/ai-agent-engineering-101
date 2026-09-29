#!/bin/sh
# Main submission: 3 conditions x 3 repeats with one model.
# Conditions run in parallel; each appends whole rows to the shared results.csv.
# Usage: sh run_all.sh [model] [out.csv] [logdir] [repeats]
MODEL=${1:-claude-haiku-4-5}
OUT=${2:-results.csv}
LOGS=${3:-logs}
REPEATS=${4:-3}
cd "$(dirname "$0")"
for c in free tagged structured; do
  (for r in $(seq 1 "$REPEATS"); do
     python run.py --condition "$c" --repeat "$r" --model "$MODEL" --out "$OUT" --logs "$LOGS" > /dev/null
   done) &
done
wait
