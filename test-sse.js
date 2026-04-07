const http = require('http');

const options = {
  hostname: '127.0.0.1',
  port: 4000,
  path: '/extension/sync',
  method: 'GET',
  timeout: 5000
};

console.log('[TEST-SSE] Testing /extension/sync endpoint...');

const req = http.request(options, (res) => {
  console.log('[TEST-SSE] Connection Status:', res.statusCode);
  console.log('[TEST-SSE] Content-Type:', res.headers['content-type']);
  
  let messageCount = 0;
  const startTime = Date.now();
  
  res.on('data', (chunk) => {
    messageCount++;
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    const lines = chunk.toString().split('\n').filter(l => l.trim());
    console.log(`[TEST-SSE] Received chunk #${messageCount} at +${elapsed}s (${lines.length} lines)`);
    
    if (messageCount <= 3) {
      lines.slice(0, 2).forEach(l => {
        const shortLine = l.length > 70 ? l.substring(0, 70) + '...' : l;
        console.log(`  > ${shortLine}`);
      });
    }
  });
  
  res.on('end', () => {
    console.log('[TEST-SSE] Connection closed');
    process.exit(0);
  });
});

req.on('error', (err) => {
  console.log('[TEST-SSE] Connection error:', err.message);
  process.exit(1);
});

req.on('timeout', () => {
  console.log('[TEST-SSE] Timeout after 5s - connection still active');
  req.destroy();
  process.exit(0);
});

// Auto-close after 8 seconds
setTimeout(() => {
  console.log('[TEST-SSE] Test timeout - closing...');
  req.destroy();
  process.exit(0);
}, 8000);
