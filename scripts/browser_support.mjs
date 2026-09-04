import { createReadStream } from 'node:fs';
import { access, rm, stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(SCRIPT_DIRECTORY, '..');

const MIME_TYPES = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.drawio', 'application/xml; charset=utf-8'],
  ['.gif', 'image/gif'],
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.mjs', 'text/javascript; charset=utf-8'],
  ['.mp4', 'video/mp4'],
  ['.pdf', 'application/pdf'],
  ['.png', 'image/png'],
  ['.svg', 'image/svg+xml; charset=utf-8'],
]);

function isInside(parent, candidate) {
  const relative = path.relative(parent, candidate);
  return relative === '' || (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative));
}

export function resolveRepoPath(relativePath) {
  const resolved = path.resolve(REPO_ROOT, relativePath);
  if (!isInside(REPO_ROOT, resolved)) {
    throw new Error('Path must remain inside the repository: ' + relativePath);
  }
  return resolved;
}

export function findChrome() {
  const candidates = [
    process.env.CHROME_PATH,
    process.platform === 'win32' ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' : null,
    process.platform === 'win32' ? 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe' : null,
    process.platform === 'darwin' ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : null,
    process.platform === 'linux' ? '/usr/bin/google-chrome' : null,
    process.platform === 'linux' ? '/usr/bin/google-chrome-stable' : null,
    process.platform === 'linux' ? '/usr/bin/chromium' : null,
    process.platform === 'linux' ? '/usr/bin/chromium-browser' : null,
  ].filter(Boolean);

  return candidates.reduce(async (foundPromise, candidate) => {
    const found = await foundPromise;
    if (found) return found;
    try {
      await access(candidate);
      return candidate;
    } catch {
      return null;
    }
  }, Promise.resolve(null)).then((found) => {
    if (!found) throw new Error('Chrome executable not found. Set CHROME_PATH.');
    return found;
  });
}

export async function startStaticServer({ contentOverrides = new Map() } = {}) {
  const server = createServer(async (request, response) => {
    try {
      const requestUrl = new URL(request.url || '/', 'http://127.0.0.1');
      const decodedPath = decodeURIComponent(requestUrl.pathname);
      const requestName = decodedPath.replace(/^\/+/, '').split(path.sep).join('/');
      const overridden = contentOverrides.get(requestName);
      if (overridden !== undefined) {
        const value = Buffer.isBuffer(overridden) ? overridden : Buffer.from(overridden);
        response.writeHead(200, {
          'Cache-Control': 'no-store',
          'Connection': 'close',
          'Content-Length': value.length,
          'Content-Type': MIME_TYPES.get(path.extname(requestName).toLowerCase()) || 'application/octet-stream',
        });
        response.end(request.method === 'HEAD' ? undefined : value);
        return;
      }
      let target = resolveRepoPath('.' + decodedPath);
      const targetStat = await stat(target);
      if (targetStat.isDirectory()) {
        target = path.join(target, 'index.html');
      }
      if (!isInside(REPO_ROOT, target)) {
        response.writeHead(403).end('Forbidden');
        return;
      }
      const fileStat = await stat(target);
      if (!fileStat.isFile()) {
        response.writeHead(404).end('Not found');
        return;
      }
      response.writeHead(200, {
        'Cache-Control': 'no-store',
        'Connection': 'close',
        'Content-Length': fileStat.size,
        'Content-Type': MIME_TYPES.get(path.extname(target).toLowerCase()) || 'application/octet-stream',
      });
      if (request.method === 'HEAD') {
        response.end();
        return;
      }
      createReadStream(target).pipe(response);
    } catch {
      response.writeHead(404).end('Not found');
    }
  });

  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address();
  if (!address || typeof address === 'string') {
    throw new Error('Failed to bind the local static server.');
  }
  return {
    origin: 'http://127.0.0.1:' + address.port,
    close: () => new Promise((resolve) => {
      server.close(() => resolve());
      if (typeof server.closeAllConnections === 'function') server.closeAllConnections();
    }),
  };
}

export async function removeOwnedTempDirectory(directory, expectedPrefix) {
  if (!directory) return;
  const resolved = path.resolve(directory);
  const tempRoot = path.resolve(os.tmpdir());
  if (!isInside(tempRoot, resolved) || resolved === tempRoot || !path.basename(resolved).startsWith(expectedPrefix)) {
    throw new Error('Refusing to remove an unexpected temporary directory: ' + resolved);
  }
  await rm(resolved, {
    recursive: true,
    force: true,
    maxRetries: 12,
    retryDelay: 200,
  });
}
