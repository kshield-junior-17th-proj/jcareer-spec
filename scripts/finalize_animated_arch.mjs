#!/usr/bin/env node

import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';

const checkOnly = process.argv.includes('--check');
const sourceArgument = process.argv.slice(2).find((argument) => !argument.startsWith('--'));
const sourcePath = resolve(sourceArgument || 'assets/JCAREER_PLATFORM_ANIMATED.svg');
const specArgument = process.argv.find((argument) => argument.startsWith('--spec='));
const specPath = resolve(specArgument?.slice('--spec='.length) || 'assets/JCAREER_PLATFORM_ANIMATED.spec.json');
const specBytes = Buffer.from(readFileSync(specPath, 'utf8').replace(/\r\n?/g, '\n'), 'utf8');
const spec = JSON.parse(specBytes.toString('utf8'));
const specHash = createHash('sha256').update(specBytes).digest('hex');
const sourceInput = readFileSync(sourcePath, 'utf8');
const input = sourceInput.replace(/\r\n?/g, '\n');
const reducedMotionRule = '@media (prefers-reduced-motion: reduce){.motion-dot{display:none}}';
const sourceMetadata = `<metadata id="jcareer-animated-source" data-spec-sha256="${specHash}"/>`;

const escapeXml = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;');

const estimatedTextWidth = (value, fontSize) => [...String(value)].reduce((width, character) => {
  if (/[ᄀ-ᇿ⺀-鿿가-힯]/u.test(character)) return width + fontSize;
  if (/\s/u.test(character)) return width + fontSize * 0.34;
  if (/[·/×→]/u.test(character)) return width + fontSize * 0.62;
  return width + fontSize * 0.56;
}, 0);

let output = input;
if (/<metadata id="jcareer-animated-source"[^>]*\/>/.test(output)) {
  output = output.replace(/<metadata id="jcareer-animated-source"[^>]*\/>/, sourceMetadata);
} else {
  output = output.replace(/(<title>.*?<\/title>)/, `$1\n${sourceMetadata}`);
}
if (!output.includes(reducedMotionRule)) {
  output = output.replace('@keyframes dm', `${reducedMotionRule}@keyframes dm`);
}
output = output.replace(
  /<circle(?![^>]*\bclass="motion-dot")([^>]*)><animateMotion\b/g,
  '<circle class="motion-dot"$1><animateMotion',
);
output = output.replace(/\bbegin="(?!-)([0-9]+(?:\.[0-9]+)?)s"/g, (match, rawSeconds) => {
  const seconds = Number(rawSeconds);
  return seconds > 0 ? `begin="-${rawSeconds}s"` : match;
});

if (spec.labelBackplates === true) {
  for (const node of spec.nodes) {
    const marker = `data-node-label="${escapeXml(node.id)}"`;
    if (output.includes(marker)) continue;
    const labelWidth = estimatedTextWidth(node.label, 13);
    const subWidth = estimatedTextWidth(node.sub, 9.5);
    const width = Math.max(64, Math.ceil(Math.max(labelWidth, subWidth) + 14));
    const x = (node.x - width / 2).toFixed(1);
    const y = (node.y + 28).toFixed(1);
    const labelText = `<text x="${node.x}" y="${node.y + 38}" text-anchor="middle" font-size="13" font-weight="700" fill="#16202E">${escapeXml(node.label)}</text>`;
    const backdrop = `<rect class="node-label-backdrop" ${marker} x="${x}" y="${y}" width="${width}" height="31" rx="5" fill="#FBFCFE" fill-opacity="0.94"/>`;
    if (!output.includes(labelText)) {
      throw new Error(`Unable to locate node label for backdrop: ${node.id}`);
    }
    output = output.replace(labelText, `${backdrop}${labelText}`);
  }
}
output = output.replace(/\r\n?/g, '\n').replace(/[ \t]+$/gm, '');

// AWS artwork can carry the same internal IDs every time one official icon is
// inlined. Keep the first ID as the shared reference target and suffix later
// occurrences so the final self-contained document remains valid XML/SVG.
const embeddedIdCounts = new Map();
output = output.replace(/\bid="([^"]+)"/g, (match, id) => {
  const count = (embeddedIdCounts.get(id) || 0) + 1;
  embeddedIdCounts.set(id, count);
  return count === 1 ? match : `id="${id}__${count}"`;
});

const motionCount = (output.match(/<animateMotion\b/g) || []).length;
const guardedMotionCount = (output.match(/<circle class="motion-dot"[^>]*><animateMotion\b/g) || []).length;
const expectedMotionCount = spec.journeys.reduce((total, journey) => total + journey.hops.length, 0);
if (motionCount !== expectedMotionCount || guardedMotionCount !== motionCount) {
  throw new Error(`Unexpected motion element count: ${guardedMotionCount}/${motionCount}`);
}

const ids = [...output.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
const uniqueIds = new Set(ids);
const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
if (duplicateIds.length) {
  throw new Error(`Duplicate SVG IDs: ${duplicateIds.join(', ')}`);
}
if (/(?:href|src)="https?:\/\//.test(output) || /<image\b/.test(output)) {
  throw new Error('Animated SVG must remain self-contained.');
}

if (checkOnly) {
  if (output !== input) throw new Error('Animated SVG is not finalized.');
} else if (output !== sourceInput) {
  writeFileSync(sourcePath, output, 'utf8');
}

console.log(`animated SVG: ${checkOnly ? 'PASS' : 'finalized'}; motion ${guardedMotionCount}/${motionCount}; IDs ${uniqueIds.size}/${ids.length}`);
