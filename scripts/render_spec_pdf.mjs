#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
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

async function runChrome(executable, argumentsList) {
  const child = spawn(executable, argumentsList, {
    stdio: ['ignore', 'ignore', 'pipe'],
    windowsHide: true,
  });
  let diagnostic = '';
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => {
    if (diagnostic.length < 8000) diagnostic += chunk;
  });
  const exitCode = await new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('exit', (code) => resolve(code));
  });
  if (exitCode !== 0) {
    throw new Error('Chrome PDF render failed (' + exitCode + '): ' + diagnostic.trim());
  }
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
  const temporaryPdf = path.join(profileDirectory, 'rendered.pdf');
  const server = await startStaticServer();

  try {
    const chrome = await findChrome();
    const sourceUrl = server.origin + '/' + sourceName.split('/').map(encodeURIComponent).join('/');
    await runChrome(chrome, [
      '--headless=new',
      '--disable-gpu',
      '--disable-extensions',
      '--no-first-run',
      '--no-default-browser-check',
      '--no-pdf-header-footer',
      '--virtual-time-budget=5000',
      '--user-data-dir=' + profileDirectory,
      '--print-to-pdf=' + temporaryPdf,
      sourceUrl,
    ]);

    const rendered = await readFile(temporaryPdf);
    if (!rendered.subarray(0, 5).equals(Buffer.from('%PDF-'))) {
      throw new Error('Chrome output is not a PDF.');
    }
    const finalBytes = Buffer.concat([rendered, sourceMarker(sourceName, sourceBytes)]);
    await writeFile(outputPath, finalBytes);
    console.log(
      'PDF rendered and source-bound: ' + repositoryName(outputPath) +
      ' <- ' + sourceName +
      ' (' + finalBytes.length + ' bytes)',
    );
  } finally {
    await server.close();
    await removeOwnedTempDirectory(profileDirectory, 'jcareer-pdf-');
  }
}

main().catch((error) => {
  console.error('::error::' + error.message);
  process.exitCode = 1;
});
