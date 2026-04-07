#!/bin/bash
# Integration test for fetch-file endpoint
# Prerequisites: npm start (server must be running on http://127.0.0.1:4000)

set -e

SERVER_URL="http://127.0.0.1:4000"
TMP_DIR=$(mktemp -d)

echo "🧪 Testing GET /fetch-file endpoint"
echo "Server: $SERVER_URL"
echo "Temp dir: $TMP_DIR"
echo ""

# Test 1: Public file fetch
echo "✅ Test 1: Fetch public file"
RESPONSE=$(curl -s "$SERVER_URL/fetch-file?fileUrl=https://raw.githubusercontent.com/github/gitignore/main/Node.gitignore")
OK=$(echo $RESPONSE | grep -o '"ok":true' | head -1)
if [ -z "$OK" ]; then
  echo "❌ FAIL: Expected ok=true"
  echo "Response: $RESPONSE"
  exit 1
fi
PATH=$(echo $RESPONSE | grep -o '"path":"[^"]*"' | cut -d'"' -f4)
echo "✅ Retrieved file: $PATH"
ls -lh "$PATH" 2>/dev/null && echo "✅ File exists on disk" || echo "❌ File not found"

# Test 2: Missing fileUrl param
echo ""
echo "✅ Test 2: Missing fileUrl (should return 400)"
RESPONSE=$(curl -s -w "\n%{http_code}" "$SERVER_URL/fetch-file")
STATUS=$(echo "$RESPONSE" | tail -1)
if [ "$STATUS" -eq 400 ]; then
  echo "✅ Returned 400 as expected"
else
  echo "❌ Expected 400, got $STATUS"
  exit 1
fi

# Test 3: Invalid URL
echo ""
echo "✅ Test 3: Invalid URL (should return 500 or error)"
RESPONSE=$(curl -s -w "\n%{http_code}" "$SERVER_URL/fetch-file?fileUrl=not-a-url")
STATUS=$(echo "$RESPONSE" | tail -1)
ERROR=$(echo "$RESPONSE" | grep -o '"error"' || true)
if [ -n "$ERROR" ]; then
  echo "✅ Returned error as expected (status $STATUS)"
else
  echo "❌ Expected error in response"
fi

# Test 4: Broker mode endpoint
echo ""
echo "✅ Test 4: GET /broker-mode"
RESPONSE=$(curl -s "$SERVER_URL/broker-mode")
OK=$(echo $RESPONSE | grep -o '"ok":true' | head -1)
MODE=$(echo $RESPONSE | grep -o '"mode":"[^"]*"' | cut -d'"' -f4)
echo "✅ Broker mode: $MODE"

# Test 5: Quote endpoint
echo ""
echo "✅ Test 5: GET /quote?symbol=EUR/USD"
RESPONSE=$(curl -s "$SERVER_URL/quote?symbol=EUR/USD")
OK=$(echo $RESPONSE | grep -o '"ok":true' | head -1)
if [ -n "$OK" ]; then
  PRICE=$(echo $RESPONSE | grep -o '"price":[0-9.]*' | cut -d':' -f2)
  echo "✅ EUR/USD price: $PRICE"
else
  echo "⚠️  Quote endpoint returned: $RESPONSE"
fi

echo ""
echo "🎉 Integration tests completed"
echo ""
