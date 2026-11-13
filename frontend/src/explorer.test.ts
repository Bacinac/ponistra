import { describe, expect, it } from 'vitest';
import { between, formatSize, sortNodes } from './explorer';
import type { TreeNode } from './tree';

function node(title: string, fields: Partial<TreeNode> = {}): TreeNode {
  return {
    id: title,
    parent: null,
    kind: 'document',
    title,
    locale: 'hr',
    updated_at: '2026-10-16T10:00:00Z',
    updated_by: null,
    size: null,
    media_type: null,
    picture: null,
    holds: null,
    origin: null,
    extension: null,
    href: null,
    description: '',
    trashed_at: null,
    original: null,
    macros: null,
    imported: null,
    company: false,
    confined: false,
    notes: false,
    links: false,
    boards: false,
    columns: null,
    agent_folder: null,
    ...fields,
  };
}

const titles = (nodes: TreeNode[]) => nodes.map((n) => n.title);

describe('sortNodes', () => {
  const nodes = [
    node('Čvor', { updated_at: '2026-10-16T12:00:00Z' }),
    node('Arhiva', { kind: 'folder' }),
    node('cesta', { kind: 'file', size: 900 }),
    node('Zapisnik 10', { size: 50 }),
    node('Zapisnik 9'),
  ];

  it('keeps folders first and names in Croatian order, numbers by value', () => {
    expect(titles(sortNodes(nodes, { key: 'title', descending: false }))).toEqual([
      'Arhiva',
      'cesta',
      'Čvor',
      'Zapisnik 9',
      'Zapisnik 10',
    ]);
  });

  it('keeps folders first when the order is reversed', () => {
    expect(titles(sortNodes(nodes, { key: 'size', descending: true }))).toEqual([
      'Arhiva',
      'cesta',
      'Zapisnik 10',
      'Zapisnik 9',
      'Čvor',
    ]);
  });

  it('orders by the time of the last change', () => {
    expect(titles(sortNodes(nodes, { key: 'updated_at', descending: true }))[1]).toBe('Čvor');
  });
});

describe('between', () => {
  it('takes the range in either direction', () => {
    expect(between(['a', 'b', 'c', 'd'], 'c', 'a')).toEqual(['a', 'b', 'c']);
  });

  it('falls back to the clicked item when the anchor is gone', () => {
    expect(between(['a', 'b'], 'x', 'b')).toEqual(['b']);
  });
});

describe('formatSize', () => {
  const format = (value: number) => new Intl.NumberFormat('hr-HR').format(value);

  it('steps through the units with one decimal', () => {
    expect(formatSize(512, format)).toBe('512 B');
    expect(formatSize(1_234_567, format)).toBe('1,2 MB');
  });
});
