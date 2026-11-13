import { readFileSync, statfsSync } from 'node:fs';
import { cpus, loadavg } from 'node:os';

const KIB = 1024;

const meminfo = () => {
  const found = new Map();
  for (const line of readFileSync('/proc/meminfo', 'utf8').split('\n')) {
    const [, name, kib] = /^(\w+):\s+(\d+) kB$/.exec(line) ?? [];
    if (name) found.set(name, Number(kib) * KIB);
  }
  for (const name of ['MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'])
    if (!found.has(name)) throw new Error(`/proc/meminfo has no ${name}`);
  return found;
};

/** The machine the workspace runs on as the kernel sees it now, and the disk of the projects:
    {at, load, cpus, memory, swap, disk, error}. The load is the whole machine's, so it is
    weighed against every processor the kernel has rather than the ones the workspace is given. */
export const hostOf = (root) => {
  const at = new Date().toISOString();
  try {
    const memory = meminfo();
    const disk = statfsSync(root);
    return {
      at,
      load: loadavg()[0],
      cpus: cpus().length,
      memory: { total: memory.get('MemTotal'), available: memory.get('MemAvailable') },
      swap: memory.get('SwapTotal') ? { total: memory.get('SwapTotal'), free: memory.get('SwapFree') } : null,
      disk: { total: disk.blocks * disk.bsize, free: disk.bavail * disk.bsize },
      error: null,
    };
  } catch (error) {
    console.error('the machine of the workspace could not be measured', error);
    return { at, load: null, cpus: null, memory: null, swap: null, disk: null, error: 'unread' };
  }
};
