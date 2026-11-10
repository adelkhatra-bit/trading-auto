#!/usr/bin/env bash
# Smoke tests for the current Express backend routes.
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:4000}"

echo "Checking backend health"
HEALTH="$(curl --fail --silent --show-error "$BASE_URL/health")"
echo "$HEALTH" | grep -q '"ok":true'
echo "OK /health"

echo "Checking broker mode endpoint"
BROKER="$(curl --fail --silent --show-error "$BASE_URL/broker-mode")"
echo "$BROKER" | grep -q '"ok":true'
echo "$BROKER" | grep -q '"mode":'
echo "OK /broker-mode"

echo "Backend smoke tests passed"
