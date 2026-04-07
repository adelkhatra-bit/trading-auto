const fs = require('fs');
const os = require('os');
const path = require('path');
const { URL } = require('url');

async function fetchFile({ fileUrl, accessMethod = 'public', bearerToken = '' }) {
  if (!fileUrl) throw new Error('fileUrl is required');

  let parsed;
  try {
    parsed = new URL(fileUrl);
  } catch (err) {
    throw new Error('fileUrl is malformed');
  }

  const headers = {};
  const method = 'GET';

  if (accessMethod === 'token') {
    if (!bearerToken) {
      throw new Error('Bearer token required for accessMethod=token');
    }
    headers.Authorization = `Bearer ${bearerToken}`;
  }

  if (!['public', 'token', 'onedrive'].includes(accessMethod)) {
    throw new Error('ACCESS_METHOD must be public, token or onedrive');
  }

  const response = await fetch(fileUrl, { method, headers });
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`Unable to fetch file (${response.status}): ${text}`);
  }

  const buffer = await response.arrayBuffer();
  const data = Buffer.from(buffer);

  const baseName = path.basename(parsed.pathname) || 'downloaded-file';
  const safeName = baseName.replace(/[^a-zA-Z0-9._-]/g, '_');
  const randomSuffix = Math.random().toString(36).slice(2, 8);

  const targetDir = path.join(os.tmpdir(), 'trading-auto-files');
  await fs.promises.mkdir(targetDir, { recursive: true });

  const filePath = path.join(targetDir, `${Date.now()}-${randomSuffix}-${safeName}`);
  await fs.promises.writeFile(filePath, data);

  return { path: filePath };
}

module.exports = { fetchFile };
