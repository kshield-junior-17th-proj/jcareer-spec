import { access, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';

const EDGE_CANDIDATES = process.platform === 'win32'
  ? [
      'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
      'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
      'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    ]
  : [
      '/usr/bin/microsoft-edge',
      '/usr/bin/google-chrome',
      '/usr/bin/chromium',
    ];

class CdpClient {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
    this.socket.addEventListener('message', (event) => {
      const payload = JSON.parse(event.data);
      if (!payload.id) return;
      const waiter = this.pending.get(payload.id);
      if (!waiter) return;
      this.pending.delete(payload.id);
      if (payload.error) waiter.reject(new Error(JSON.stringify(payload.error)));
      else waiter.resolve(payload.result || {});
    });
  }

  async open() {
    if (this.socket.readyState === WebSocket.OPEN) return;
    await new Promise((resolve, reject) => {
      this.socket.addEventListener('open', resolve, { once: true });
      this.socket.addEventListener('error', reject, { once: true });
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket.close();
  }
}

async function findBrowser() {
  for (const candidate of EDGE_CANDIDATES) {
    try {
      await access(candidate);
      return candidate;
    } catch {
      // Continue to the next supported Chromium browser.
    }
  }
  throw new Error('A supported Chromium browser was not found.');
}

async function waitForDevTools(profileDirectory) {
  const activePort = path.join(profileDirectory, 'DevToolsActivePort');
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    try {
      const [port] = (await readFile(activePort, 'utf8')).trim().split(/\r?\n/);
      if (port) return Number(port);
    } catch {
      // Browser startup is still in progress.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error('Timed out waiting for the browser DevTools endpoint.');
}

async function waitForDocument(client) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    const result = await client.send('Runtime.evaluate', {
      expression: 'document.readyState',
      returnByValue: true,
    });
    if (result.result?.value === 'complete') return;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error('Timed out waiting for the SVG document to load.');
}

async function main() {
  const [inputArgument, outputArgument, frameArgument = '24', fpsArgument = '12'] = process.argv.slice(2);
  if (!inputArgument || !outputArgument) {
    throw new Error('Usage: node scripts/render_animated_architecture.mjs <input.svg> <output-directory> [frames] [fps]');
  }

  const input = path.resolve(inputArgument);
  const output = path.resolve(outputArgument);
  const frames = Number(frameArgument);
  const fps = Number(fpsArgument);
  if (!Number.isInteger(frames) || frames < 2 || !Number.isFinite(fps) || fps <= 0) {
    throw new Error('frames must be an integer >= 2 and fps must be positive.');
  }
  await access(input);
  await mkdir(output, { recursive: false });

  const profileDirectory = await import('node:fs/promises').then(({ mkdtemp }) =>
    mkdtemp(path.join(os.tmpdir(), 'jcareer-architecture-render-')),
  );
  const browser = await findBrowser();
  const child = spawn(browser, [
    '--headless=new',
    '--disable-gpu',
    '--disable-background-mode',
    '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding',
    '--hide-scrollbars',
    '--no-first-run',
    '--remote-debugging-port=0',
    '--user-data-dir=' + profileDirectory,
    '--window-size=1800,980',
    pathToFileURL(input).href,
  ], { stdio: 'ignore' });

  let client;
  try {
    const port = await waitForDevTools(profileDirectory);
    const targets = await fetch(`http://127.0.0.1:${port}/json/list`).then((response) => response.json());
    const target = targets.find((item) => item.type === 'page');
    if (!target?.webSocketDebuggerUrl) throw new Error('No page target was exposed by the browser.');
    client = new CdpClient(target.webSocketDebuggerUrl);
    await client.open();
    await client.send('Page.enable');
    await client.send('Runtime.enable');
    await client.send('Emulation.setDeviceMetricsOverride', {
      width: 1800,
      height: 980,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await client.send('Page.navigate', { url: pathToFileURL(input).href });
    await waitForDocument(client);

    for (let index = 0; index < frames; index += 1) {
      const seconds = index / fps;
      await client.send('Runtime.evaluate', {
        expression: `(() => {
          const root = document.documentElement;
          if (typeof root.pauseAnimations === 'function') root.pauseAnimations();
          if (typeof root.setCurrentTime === 'function') root.setCurrentTime(${seconds});
          for (const animation of document.getAnimations()) {
            animation.pause();
            animation.currentTime = ${seconds * 1000};
          }
          return true;
        })()`,
        awaitPromise: true,
        returnByValue: true,
      });
      const screenshot = await client.send('Page.captureScreenshot', {
        format: 'png',
        fromSurface: true,
        captureBeyondViewport: false,
      });
      const frameName = `frame-${String(index).padStart(3, '0')}.png`;
      await writeFile(path.join(output, frameName), Buffer.from(screenshot.data, 'base64'));
    }
  } finally {
    if (client) {
      try {
        await client.send('Browser.close');
      } catch {
        // The renderer process may already be exiting.
      }
      client.close();
    }
    await new Promise((resolve) => {
      if (child.exitCode !== null) resolve();
      else {
        child.once('exit', resolve);
        setTimeout(() => {
          child.kill();
          resolve();
        }, 3_000);
      }
    });
    await rm(profileDirectory, { recursive: true, force: true, maxRetries: 12, retryDelay: 100 });
  }

  process.stdout.write(`Rendered ${frames} frames at ${fps} fps to ${output}\n`);
}

main().catch((error) => {
  process.stderr.write(error.stack + '\n');
  process.exitCode = 1;
});
