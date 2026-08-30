#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import {
  REPO_ROOT,
  findChrome,
  removeOwnedTempDirectory,
  resolveRepoPath,
  startStaticServer,
} from './browser_support.mjs';

function repositoryName(absolutePath) {
  return path.relative(REPO_ROOT, absolutePath).split(path.sep).join('/');
}

function sourceMarker(sourceName, sourceBytes) {
  const digest = createHash('sha256').update(sourceBytes).digest('hex');
  return Buffer.from(
    '\n% JCAREER_HTML_SOURCE: ' + sourceName +
    '\n% JCAREER_HTML_SHA256: ' + digest + '\n',
    'ascii',
  );
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitFor(check, description, timeoutMilliseconds = 12000) {
  const deadline = Date.now() + timeoutMilliseconds;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const value = await check();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await delay(80);
  }
  const suffix = lastError ? ' Last error: ' + lastError.message : '';
  throw new Error('Timed out waiting for ' + description + '.' + suffix);
}

class CdpClient {
  constructor(webSocketUrl) {
    if (typeof WebSocket === 'undefined') {
      throw new Error('PDF rendering requires the WebSocket API available in Node.js 22 or newer.');
    }
    this.nextId = 1;
    this.pending = new Map();
    this.socket = new WebSocket(webSocketUrl);
    this.ready = new Promise((resolve, reject) => {
      this.socket.addEventListener('open', resolve, { once: true });
      this.socket.addEventListener('error', () => reject(new Error('Chrome DevTools WebSocket failed.')), { once: true });
    });
    this.socket.addEventListener('message', async (event) => {
      const raw = typeof event.data === 'string'
        ? event.data
        : event.data && typeof event.data.text === 'function'
          ? await event.data.text()
          : Buffer.from(event.data).toString('utf8');
      const message = JSON.parse(raw);
      if (!message.id || !this.pending.has(message.id)) return;
      const pending = this.pending.get(message.id);
      this.pending.delete(message.id);
      clearTimeout(pending.timeout);
      if (message.error) pending.reject(new Error(message.error.message));
      else pending.resolve(message.result);
    });
    this.socket.addEventListener('close', () => {
      for (const pending of this.pending.values()) {
        clearTimeout(pending.timeout);
        pending.reject(new Error('Chrome DevTools WebSocket closed.'));
      }
      this.pending.clear();
    });
  }

  async send(method, params = {}, timeoutMilliseconds = 12000) {
    await this.ready;
    const id = this.nextId++;
    const response = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error('Chrome DevTools command timed out: ' + method));
      }, timeoutMilliseconds);
      this.pending.set(id, { resolve, reject, timeout });
    });
    this.socket.send(JSON.stringify({ id, method, params }));
    return response;
  }

  close() {
    if (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING) {
      this.socket.close();
    }
  }
}

async function evaluate(client, expression) {
  const response = await client.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error('Browser evaluation failed: ' + JSON.stringify(response.exceptionDetails));
  }
  return response.result.value;
}

async function createPageClient(debugPort) {
  const endpoint = 'http://127.0.0.1:' + debugPort + '/json/new?' + encodeURIComponent('about:blank');
  const target = await waitFor(async () => {
    const response = await fetch(endpoint, { method: 'PUT' });
    if (!response.ok) return null;
    const value = await response.json();
    return value.webSocketDebuggerUrl ? value : null;
  }, 'a Chrome page target');
  const client = new CdpClient(target.webSocketDebuggerUrl);
  await client.send('Page.enable');
  await client.send('Runtime.enable');
  await client.send('Emulation.setEmulatedMedia', {
    media: 'print',
    features: [{ name: 'prefers-reduced-motion', value: 'reduce' }],
  });
  return client;
}

async function navigate(client, url) {
  const result = await client.send('Page.navigate', { url });
  if (result.errorText) throw new Error('Navigation failed: ' + result.errorText);
  await waitFor(
    async () => (await evaluate(client, 'document.readyState')) === 'complete',
    'document load: ' + url,
  );
  await evaluate(
    client,
    '(() => { Array.from(document.images).forEach((image) => { image.loading = "eager"; }); const ready = Promise.all([document.fonts ? document.fonts.ready : Promise.resolve(), ...Array.from(document.images).map((image) => image.complete ? Promise.resolve() : new Promise((resolve) => { image.addEventListener("load", resolve, { once: true }); image.addEventListener("error", resolve, { once: true }); }))]); return Promise.race([ready, new Promise((resolve) => setTimeout(resolve, 5000))]).then(() => true); })()',
  );
}

async function rewriteRelativeLinks(client) {
  return evaluate(
    client,
    `(() => {
      const canonical = document.querySelector('link[rel="canonical"]')?.href || '';
      if (!canonical.startsWith('https://')) throw new Error('The HTML source is missing an HTTPS canonical URL.');
      let rewritten = 0;
      document.querySelectorAll('a[href]').forEach((anchor) => {
        const href = anchor.getAttribute('href');
        if (!href || href.startsWith('#') || /^(?:[a-z][a-z0-9+.-]*:|\\/\\/)/i.test(href)) return;
        anchor.href = new URL(href, canonical).href;
        rewritten += 1;
      });
      return { canonical, rewritten };
    })()`,
  );
}

async function main() {
  const [sourceArgument, outputArgument] = process.argv.slice(2);
  if (!sourceArgument || !outputArgument) {
    throw new Error('Usage: node scripts/render_spec_pdf.mjs <source.html> <output.pdf>');
  }

  const sourcePath = resolveRepoPath(sourceArgument);
  const outputPath = resolveRepoPath(outputArgument);
  if (path.extname(sourcePath).toLowerCase() !== '.html' || path.extname(outputPath).toLowerCase() !== '.pdf') {
    throw new Error('The source must be HTML and the output must be PDF.');
  }
  if (sourcePath === outputPath) {
    throw new Error('Source and output paths must differ.');
  }

  const sourceBytes = await readFile(sourcePath);
  const sourceName = repositoryName(sourcePath);
  const profileDirectory = await mkdtemp(path.join(os.tmpdir(), 'jcareer-pdf-'));
  const server = await startStaticServer();
  let chromeProcess = null;
  let chromeExited = false;
  let client = null;

  try {
    const chrome = await findChrome();
    chromeProcess = spawn(chrome, [
      '--headless=new',
      '--disable-gpu',
      '--disable-extensions',
      '--no-first-run',
      '--no-default-browser-check',
      '--remote-debugging-port=0',
      '--remote-allow-origins=*',
      '--user-data-dir=' + profileDirectory,
      'about:blank',
    ], {
      stdio: 'ignore',
      windowsHide: true,
    });
    chromeProcess.once('exit', () => {
      chromeExited = true;
    });

    const portFile = path.join(profileDirectory, 'DevToolsActivePort');
    const debugPort = await waitFor(async () => {
      if (chromeExited) throw new Error('Chrome exited before opening DevTools.');
      try {
        const lines = (await readFile(portFile, 'utf8')).trim().split(/\r?\n/);
        return /^\d+$/.test(lines[0]) ? Number(lines[0]) : null;
      } catch {
        return null;
      }
    }, 'Chrome DevTools port');

    client = await createPageClient(debugPort);
    const sourceUrl = server.origin + '/' + sourceName.split('/').map(encodeURIComponent).join('/');
    await navigate(client, sourceUrl);
    const linkResult = await rewriteRelativeLinks(client);
    if (linkResult.rewritten < 1) {
      throw new Error('No relative document links were rewritten for the PDF.');
    }
    const printResult = await client.send('Page.printToPDF', {
      printBackground: true,
      preferCSSPageSize: true,
      displayHeaderFooter: false,
    }, 60000);
    const rendered = Buffer.from(printResult.data || '', 'base64');
    if (!rendered.subarray(0, 5).equals(Buffer.from('%PDF-'))) {
      throw new Error('Chrome output is not a PDF.');
    }
    const finalBytes = Buffer.concat([rendered, sourceMarker(sourceName, sourceBytes)]);
    await writeFile(outputPath, finalBytes);
    console.log(
      'PDF rendered and source-bound: ' + repositoryName(outputPath) +
      ' <- ' + sourceName + ' (' + finalBytes.length + ' bytes; ' +
      linkResult.rewritten + ' public links)',
    );
  } finally {
    if (client) {
      await Promise.race([
        client.send('Browser.close').catch(() => null),
        delay(500),
      ]);
      client.close();
    }
    if (chromeProcess && !chromeExited) {
      chromeProcess.kill();
      await Promise.race([
        new Promise((resolve) => chromeProcess.once('exit', resolve)),
        delay(1200),
      ]);
      if (process.platform === 'win32' && !chromeExited) {
        spawnSync('taskkill', ['/PID', String(chromeProcess.pid), '/T', '/F'], {
          stdio: 'ignore',
          windowsHide: true,
        });
      }
    }
    await delay(300);
    await server.close();
    await removeOwnedTempDirectory(profileDirectory, 'jcareer-pdf-');
  }
}

main().catch((error) => {
  console.error('::error::' + error.message);
  process.exitCode = 1;
});
