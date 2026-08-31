#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';

const root = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(?:([A-Za-z]):)/, '$1:'));
const option = (name) => process.argv.find((argument) => argument.startsWith(`--${name}=`))?.slice(name.length + 3);
const pngPath = path.resolve(option('png') || '');
const drawioPath = path.resolve(option('drawio') || path.join(root, 'JCAREER_ASIS_FLOW.drawio'));
const outputPath = path.resolve(option('output') || path.join(root, 'JCAREER_ASIS_FLOW.drawio.png'));

if (!option('png')) throw new Error('Pass the rendered PNG with --png=<path>.');
if (path.extname(drawioPath) !== '.drawio' || path.extname(outputPath) !== '.png') {
  throw new Error('The source must be .drawio and the output must be .png.');
}

const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const input = fs.readFileSync(pngPath);
if (!input.subarray(0, 8).equals(signature)) throw new Error('PNG signature is missing.');
const width = input.readUInt32BE(16);
const height = input.readUInt32BE(20);
if (width !== 2400 || height !== 1400) throw new Error(`Expected 2400x1400, received ${width}x${height}.`);

const crcTable = Array.from({ length: 256 }, (_, value) => {
  let current = value;
  for (let bit = 0; bit < 8; bit += 1) {
    current = (current & 1) ? (0xedb88320 ^ (current >>> 1)) : (current >>> 1);
  }
  return current >>> 0;
});

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const typeBytes = Buffer.from(type, 'ascii');
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(Buffer.concat([typeBytes, data])));
  return Buffer.concat([length, typeBytes, data, checksum]);
}

let offset = 8;
let iendOffset = -1;
while (offset + 12 <= input.length) {
  const length = input.readUInt32BE(offset);
  const type = input.toString('ascii', offset + 4, offset + 8);
  const next = offset + 12 + length;
  if (next > input.length) throw new Error(`Truncated PNG chunk: ${type}.`);
  if (type === 'IEND') {
    iendOffset = offset;
    break;
  }
  offset = next;
}
if (iendOffset < 0) throw new Error('PNG IEND chunk is missing.');

const xml = fs.readFileSync(drawioPath);
if (!xml.includes(Buffer.from('<mxfile'))) throw new Error('draw.io source lacks mxfile XML.');
const editableMetadata = pngChunk('tEXt', Buffer.concat([Buffer.from('mxfile\0', 'ascii'), xml]));
const output = Buffer.concat([input.subarray(0, iendOffset), editableMetadata, input.subarray(iendOffset)]);
fs.writeFileSync(outputPath, output);
console.log(`embedded draw.io XML in ${outputPath} (${width}x${height}, ${output.length} bytes)`);
