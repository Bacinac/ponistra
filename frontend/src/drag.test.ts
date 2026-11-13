import { describe, expect, it } from 'vitest';
import { dropped } from './drag';
import { pathOf, type Picked } from './upload';

/** A dropped file or folder as the browser's entries give it, a folder's in batches of two. */
function entry(name: string, children?: FileSystemEntry[]): FileSystemEntry {
  if (!children) {
    const file = new File([], name);
    return {
      name,
      isFile: true,
      isDirectory: false,
      file: (done: (f: File) => void) => done(file),
    } as unknown as FileSystemEntry;
  }
  return {
    name,
    isFile: false,
    isDirectory: true,
    createReader: () => {
      let at = 0;
      return {
        readEntries: (done: (batch: FileSystemEntry[]) => void) => {
          done(children.slice(at, at + 2));
          at += 2;
        },
      };
    },
  } as unknown as FileSystemEntry;
}

const transfer = (...entries: FileSystemEntry[]) =>
  ({
    items: entries.map((each) => ({ kind: 'file', webkitGetAsEntry: () => each })),
    files: [],
  }) as unknown as DataTransfer;

const paths = (picked: Picked[]) => picked.map(pathOf).sort();

describe('dropped', () => {
  it('reads every file below a dropped folder, batch after batch, past the dotted ones', async () => {
    const tree = entry('Ponude', [
      entry('Ponuda.docx'),
      entry('.DS_Store'),
      entry('Diversus', [entry('Heraldi.png'), entry('Cjenik.pdf'), entry('Nacrt.pdf')]),
      entry('.git', [entry('config')]),
      entry('Napomena.txt'),
    ]);
    const picked = await dropped(transfer(tree, entry('Logo.svg')));
    expect(paths(picked)).toEqual([
      'Logo.svg',
      'Ponude/Diversus/Cjenik.pdf',
      'Ponude/Diversus/Heraldi.png',
      'Ponude/Diversus/Nacrt.pdf',
      'Ponude/Napomena.txt',
      'Ponude/Ponuda.docx',
    ]);
    expect(picked.find(({ file }) => file.name === 'Heraldi.png')!.folders).toEqual([
      'Ponude',
      'Diversus',
    ]);
  });
});
