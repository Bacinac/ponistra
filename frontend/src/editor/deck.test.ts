import { describe, expect, it } from 'vitest';
import { fitted, FITS, lookDeclarations, type Fitting } from './deck';
import { schema } from './schema';

const nodes = [schema.nodes.paragraph.create(null, schema.text('Najam'))];

describe('fitting a box’s text', () => {
  it('shrinks by as many of PowerPoint’s steps as the measured height asks', () => {
    const fit = fitted(undefined, nodes, 300, 200);
    expect(FITS[fit.step]).toBeLessThanOrEqual(200 / 300);
    expect(FITS[fit.step - 1]).toBeGreaterThan(200 / 300);
    expect(fitted(undefined, nodes, 150, 200).step).toBe(0);
    expect(fitted({ ...fit, step: FITS.length - 1 }, nodes, 900, 200).step).toBe(FITS.length - 1);
  });

  it('grows back a step only while its text has not overflowed at it', () => {
    const shrunk: Fitting = { step: 3, nodes, rose: false, stuck: false };
    const rose = fitted(shrunk, nodes, 120, 200);
    expect(rose).toMatchObject({ step: 2, rose: true });
    const over = fitted(rose, nodes, 210, 200);
    expect(over).toMatchObject({ step: 3, stuck: true });
    expect(fitted(over, nodes, 150, 200).step).toBe(3);
    const edited = [schema.nodes.paragraph.create(null, schema.text('Najam opreme'))];
    expect(fitted(over, edited, 150, 200).step).toBe(2);
  });
});

describe('a template’s text look', () => {
  it('sets what it knows, the size of the block’s list level', () => {
    expect(
      lookDeclarations(
        {
          font: 'headings',
          size: 28,
          levels: [28, 24],
          color: '#262626',
          bold: false,
          align: 'center',
        },
        1,
      ),
    ).toEqual([
      ['font-size', 'calc(24pt * var(--fit, 1))'],
      ['font-family', 'var(--font-headings)'],
      ['color', '#262626'],
      ['font-weight', '400'],
      ['--slide-align', 'center'],
    ]);
  });

  it('leaves out what another editor wrote that is not a value of ours', () => {
    expect(
      lookDeclarations({
        font: 'x; background: url(/)',
        color: 'red; background: url(/)',
        align: 'start; x' as 'left',
        size: 9000,
      }),
    ).toEqual([]);
  });
});
