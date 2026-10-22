#!/usr/bin/env bash
set -euo pipefail
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
rift demo --scenario nav2-odom --out "$TMP/incident" >/dev/null
rift verify "$TMP/incident"
rift analyze "$TMP/incident" >/dev/null || true
rift pack "$TMP/incident" -o "$TMP/incident.rift.zip" >/dev/null
rift verify "$TMP/incident.rift.zip"
rift analyze "$TMP/incident.rift.zip" >/dev/null || true
echo "RIFT Community smoke test passed"
