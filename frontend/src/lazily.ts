import { lazy, type ComponentType } from 'react';

/** A component in a chunk of its own, which the browser loads when it is first drawn. */
export function lazily<K extends string, M extends Record<K, ComponentType<any>>>(
  load: () => Promise<M>,
  name: K,
) {
  return lazy(async () => ({ default: (await load())[name] }));
}
