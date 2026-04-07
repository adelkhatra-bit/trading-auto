/**
 * Audit Helper — Extract caller information (file, function, line)
 * Role: Enriches logs with source location metadata
 * 
 * Features:
 * - getCallerLocation() — Returns {file, function, line, sourceUrl}
 */

function getCallerLocation(depth = 2) {
  const stack = new Error().stack;
  const lines = stack.split('\n');
  
  // Skip Error + getCallerLocation + specified depth
  const targetLine = lines[depth + 2];
  if (!targetLine) return { file: 'unknown', function: 'unknown', line: 0, sourceUrl: 'unknown' };
  
  // Parse: "    at functionName (/path/to/file.js:123:45)"
  const match = targetLine.match(/at\s+([^\s]+)\s+\(([^:]+):(\d+):\d+\)/);
  
  if (match) {
    const funcName = match[1];
    const filePath = match[2];
    const lineNum = parseInt(match[3], 10);
    const fileName = filePath.split(/[\\\/]/).pop();
    
    return {
      file: fileName,
      function: funcName,
      line: lineNum,
      sourceUrl: `${filePath}#L${lineNum}`
    };
  }
  
  return { file: 'unknown', function: 'unknown', line: 0, sourceUrl: 'unknown' };
}

module.exports = { getCallerLocation };
