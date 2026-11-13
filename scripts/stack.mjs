// Reads $STACK through the source maps in the directory given; scripts/stack.sh runs it.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const FRAME = /(?:https?:\/\/[^/\s)]+)?\/assets\/([^\s/():]+\.js):(\d+):(\d+)/g;
const DIGITS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

const maps = process.argv[2];
const read = new Map();
const missing = new Set();

/** The segments of each generated line, as [column, source, line, column, name] (absolute). */
function decoded(mappings) {
  const lines = [];
  const at = [0, 0, 0, 0, 0];
  for (const line of mappings.split(';')) {
    at[0] = 0;
    const segments = [];
    for (const segment of line.split(',')) {
      if (!segment) continue;
      const fields = [];
      let value = 0;
      let shift = 0;
      for (const char of segment) {
        const digit = DIGITS.indexOf(char);
        value += (digit & 31) << shift;
        if (digit & 32) {
          shift += 5;
          continue;
        }
        fields.push(value & 1 ? -(value >>> 1) : value >>> 1);
        value = 0;
        shift = 0;
      }
      fields.forEach((delta, index) => (at[index] += delta));
      segments.push(fields.length === 1 ? [at[0]] : at.slice(0, fields.length));
    }
    lines.push(segments);
  }
  return lines;
}

function mapOf(file) {
  if (!read.has(file)) {
    const path = join(maps, `${file}.map`);
    if (!existsSync(path)) {
      read.set(file, null);
    } else {
      const map = JSON.parse(readFileSync(path, 'utf8'));
      read.set(file, { ...map, lines: decoded(map.mappings) });
    }
  }
  return read.get(file);
}

function source(file, line, column) {
  const map = mapOf(file);
  if (!map) {
    missing.add(file);
    return null;
  }
  let found = null;
  for (const segment of map.lines[line - 1] ?? []) {
    if (segment[0] > column - 1) break;
    if (segment.length > 1) found = segment;
  }
  if (!found) return null;
  const name = found.length === 5 ? ` ${map.names[found[4]]}` : '';
  const path = map.sources[found[1]].replace(/^(?:\.\.\/)+/, '');
  return `${path}:${found[2] + 1}:${found[3] + 1}${name}`;
}

const out = process.env.STACK.replace(
  FRAME,
  (whole, file, line, column) => source(file, Number(line), Number(column)) ?? whole,
);
process.stdout.write(`${out}\n`);
if (missing.size) {
  process.stderr.write(`not in this release's maps: ${[...missing].join(', ')}\n`);
  process.exit(1);
}
