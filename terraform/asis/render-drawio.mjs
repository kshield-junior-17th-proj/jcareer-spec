import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const root = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(?:([A-Za-z]):)/, '$1:'));
const repoRoot = path.resolve(root, '..', '..');
const sourceArgument = process.argv.find((argument) => argument.startsWith('--source='));
const relativeSource = sourceArgument
  ? sourceArgument.slice('--source='.length)
  : 'terraform/asis/JCAREER_ASIS_FLOW.drawio';
const sourcePath = path.resolve(repoRoot, relativeSource);
const relative = path.relative(repoRoot, sourcePath);
if (relative.startsWith('..') || path.isAbsolute(relative) || path.extname(sourcePath) !== '.drawio') {
  throw new Error('Draw.io source must remain inside the repository.');
}
const xml = fs.readFileSync(sourcePath, 'utf8');
const config = JSON.stringify({
  highlight: 'none',
  nav: false,
  resize: false,
  fit: false,
  zoom: 1,
  page: 1,
  border: 0,
  toolbar: 'none',
  dark: '0',
  lightbox: false,
  xml
});
const attribute = config
  .replaceAll('&', '&amp;')
  .replaceAll('"', '&quot;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;');

const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=2400,initial-scale=1">
  <style>
    * { box-sizing: border-box; }
    :root { color-scheme: only light; }
    html, body { width: 2400px; height: 1400px; margin: 0; overflow: hidden; background: #f5f5f5; }
    .mxgraph { width: 2400px; height: 1400px; overflow: hidden; border: 0; background: #f5f5f5; }
    .geDiagramContainer { overflow: hidden !important; }
  </style>
</head>
<body>
  <div class="mxgraph" data-mxgraph="${attribute}"></div>
  <script src="https://viewer.diagrams.net/js/viewer-static.min.js"></script>
</body>
</html>`;

const outputPath = path.join(os.tmpdir(), 'jcareer-asis-drawio-render.html');
fs.writeFileSync(outputPath, html, 'utf8');
console.log(`generated ${outputPath} (${Buffer.byteLength(html)} bytes)`);
