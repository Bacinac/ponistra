import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, postJson } from './api';
import { runJob } from './jobs';
import { inFolder, isHidden, named, placed } from './upload';

vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  postJson: vi.fn(),
}));
vi.mock('./jobs', () => ({ runJob: vi.fn() }));

describe('named', () => {
  it('keeps the extension apart from the title, in lower case', () => {
    expect(named('Ponuda 2026.PDF')).toEqual({ title: 'Ponuda 2026', extension: 'pdf' });
    expect(named('2063-001 BOM - Ber.xlsm')).toEqual({
      title: '2063-001 BOM - Ber',
      extension: 'xlsm',
    });
    expect(named('Pokazni.mp4')).toEqual({ title: 'Pokazni', extension: 'mp4' });
    expect(named('RetailUP_logo_cmyk.ai')).toEqual({
      title: 'RetailUP_logo_cmyk',
      extension: 'ai',
    });
    expect(named('baza.tar.gz')).toEqual({ title: 'baza.tar', extension: 'gz' });
  });

  it('reads no extension where the name ends in none', () => {
    for (const name of ['README', 'Ponuda v1.2', 'Dr. Ivić', '.pdf', 'Ugovor.konačno']) {
      expect(named(name)).toEqual({ title: name, extension: '' });
    }
    expect(named(`Zapis.${'a'.repeat(11)}`).extension).toBe('');
  });

  it('fits the 200 characters a title may have', () => {
    expect(named(`${'x'.repeat(250)}.pdf`).title).toHaveLength(200);
  });
});

describe('placed', () => {
  const stored = (media_type: string) => ({ sha256: 'a'.repeat(64), media_type });
  const node = { id: 'n1', kind: 'file', title: 'Cijene' };
  const docx = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

  beforeEach(() => {
    vi.mocked(postJson).mockReset().mockResolvedValue(node);
    vi.mocked(runJob).mockReset();
  });

  it('keeps a file of a kind PONISTRA does not import as the file it is', async () => {
    expect(await placed(stored('application/octet-stream'), 'Pokazni.mp4', 'f1')).toEqual({ node });
    expect(postJson).toHaveBeenCalledWith('/api/nodes', {
      kind: 'file',
      parent: 'f1',
      blob: 'a'.repeat(64),
      title: 'Pokazni',
      extension: 'mp4',
    });
    expect(runJob).not.toHaveBeenCalled();
  });

  it('tells when the file was last changed, where its disk tells', async () => {
    const changed = Date.UTC(2024, 4, 3, 10, 11, 12);
    await placed(stored('application/octet-stream'), 'Pokazni.mp4', null, changed);
    expect(postJson).toHaveBeenCalledWith(
      '/api/nodes',
      expect.objectContaining({ modified: '2024-05-03T10:11:12.000Z' }),
    );
    vi.mocked(runJob).mockResolvedValue(node);
    await placed(stored(docx), 'Cijene.docx', null, changed);
    expect(runJob).toHaveBeenCalledWith(
      'import',
      expect.objectContaining({ modified: '2024-05-03T10:11:12.000Z' }),
      'Cijene.docx',
    );
  });

  it('keeps an Office file the import cannot read as a file, and tells why', async () => {
    const refusal = new ApiError('/api/jobs/1', 422, 'unreadable');
    vi.mocked(runJob).mockRejectedValue(refusal);
    expect(await placed(stored(docx), 'Cijene.docx', null)).toEqual({ node, unimported: refusal });
    expect(postJson).toHaveBeenCalledWith(
      '/api/nodes',
      expect.objectContaining({ title: 'Cijene' }),
    );
  });

  it('keeps nothing when the import fails for a reason outside the file', async () => {
    vi.mocked(runJob).mockRejectedValue(new ApiError('/api/jobs/1', 503, 'converter_unavailable'));
    await expect(placed(stored(docx), 'Cijene.docx', null)).rejects.toThrow(
      'converter_unavailable',
    );
    expect(postJson).not.toHaveBeenCalled();
  });
});

describe('a folder uploaded', () => {
  it("puts a picked folder's files in the folders their paths name, and hides the dotted ones below it", () => {
    const file = (path: string) => {
      const made = new File([], path.split('/').at(-1)!);
      Object.defineProperty(made, 'webkitRelativePath', { value: path });
      return made;
    };
    const picked = inFolder([
      file('.Arhiva/Ponuda.pdf'),
      file('.Arhiva/.git/HEAD'),
      file('.Arhiva/2026/.~lock.Cjenik.xlsx#'),
    ]);
    expect(picked.map((each) => each.folders)).toEqual([
      ['.Arhiva'],
      ['.Arhiva', '.git'],
      ['.Arhiva', '2026'],
    ]);
    expect(picked.map(isHidden)).toEqual([false, true, true]);
    expect(isHidden({ file: new File([], '.env'), folders: [] })).toBe(false);
  });
});
