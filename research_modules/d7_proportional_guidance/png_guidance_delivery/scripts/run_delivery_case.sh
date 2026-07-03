#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${MODE:-strapdown}"
LAW="${LAW:-TTC}"
SETTINGS_PATH="${SETTINGS_PATH:-$ROOT_DIR/config/airsim_blocks_settings.json}"
TRAJECTORY_DIR="${TRAJECTORY_DIR:-$ROOT_DIR/logs/delivery}"

INTERCEPTOR="${INTERCEPTOR:-Interceptor}"
INTRUDER="${INTRUDER:-Intruder}"
INTRUDER_SPEED="${INTRUDER_SPEED:-5}"
SPEED_RATIO="${SPEED_RATIO:-2.0}"
START_RANGE_M="${START_RANGE_M:-80}"
START_LATERAL_M="${START_LATERAL_M:--20}"
INTERCEPT_ALTITUDE_M="${INTERCEPT_ALTITUDE_M:-50}"
ALTITUDE_OFFSET_M="${ALTITUDE_OFFSET_M:-20}"
RATE_HZ="${RATE_HZ:-20}"
DURATION_S="${DURATION_S:-30}"
NAVIGATION_CONSTANT="${NAVIGATION_CONSTANT:-3.0}"

mkdir -p "$TRAJECTORY_DIR"

case "$LAW" in
  TTC|ttc)
    LAW_ARGS=(--guidance-law ttc_png --ttc-soft-guidance)
    LAW_TOKEN="TTC"
    ;;
  VM|Vm|vm)
    LAW_ARGS=(--guidance-law fixed_vm_png --navigation-constant "$NAVIGATION_CONSTANT")
    LAW_TOKEN="VM"
    ;;
  *)
    echo "LAW must be TTC or VM, got: $LAW" >&2
    exit 2
    ;;
esac

COMMON_ARGS=(
  --settings-path "$SETTINGS_PATH"
  --interceptor "$INTERCEPTOR"
  --intruder "$INTRUDER"
  --enable-motion
  --duration-s "$DURATION_S"
  --rate-hz "$RATE_HZ"
  --intruder-speed "$INTRUDER_SPEED"
  --speed-ratio "$SPEED_RATIO"
  --intercept-altitude-m "$INTERCEPT_ALTITUDE_M"
  --intruder-altitude-offset-m "$ALTITUDE_OFFSET_M"
  --start-horizontal-range-m "$START_RANGE_M"
  --start-lateral-offset-m "$START_LATERAL_M"
  --trajectory-dir "$TRAJECTORY_DIR"
  --no-plot
  --print-every-n "${PRINT_EVERY_N:-10}"
)

case "$MODE" in
  truth)
    SCRIPT="examples/run_airsim_truth_png.py"
    EXTRA_ARGS=()
    ;;
  gimbal)
    SCRIPT="examples/run_airsim_gimbal_vision_png.py"
    EXTRA_ARGS=(--detector-source airsim --mesh "${MESH:-Intruder*}" --no-show-window)
    ;;
  strapdown)
    SCRIPT="examples/run_airsim_strapdown_vision_png.py"
    EXTRA_ARGS=(--detector-source airsim --mesh "${MESH:-Intruder*}" --no-show-window --no-record-preview)
    ;;
  *)
    echo "MODE must be truth, gimbal, or strapdown, got: $MODE" >&2
    exit 2
    ;;
esac

PREFIX="${TRAJECTORY_PREFIX:-delivery_${MODE}_${LAW_TOKEN}_r${START_RANGE_M}_h${ALTITUDE_OFFSET_M}}"

echo "Running MODE=$MODE LAW=$LAW_TOKEN range=${START_RANGE_M}m altitude_offset=${ALTITUDE_OFFSET_M}m"
python3 "$SCRIPT" \
  "${COMMON_ARGS[@]}" \
  "${LAW_ARGS[@]}" \
  "${EXTRA_ARGS[@]}" \
  --trajectory-prefix "$PREFIX" \
  "$@"
