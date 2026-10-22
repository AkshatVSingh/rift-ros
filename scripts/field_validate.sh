#!/usr/bin/env bash
set -euo pipefail

CONFIG="${1:-rift.json}"
CYCLES="${RIFT_VALIDATION_CYCLES:-20}"
REPORT="${RIFT_VALIDATION_REPORT:-rift-live-validation.json}"

echo "== RIFT package self-test =="
rift self-test

echo "== Configuration =="
rift validate-config "$CONFIG"

echo "== Host preflight =="
rift preflight --config "$CONFIG"

echo "== Live collector validation ($CYCLES cycles) =="
rift validate-live --config "$CONFIG" --cycles "$CYCLES" -o "$REPORT"

echo "Validation report: $REPORT"
