// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

const SENTENCE = 'ponude koje mi je Ana poslala prošli mjesec';
const TRANSLATED = 'ponude vrsta:pošta od:Ana datum:2026-09-01..2026-09-30';

/** The installation with AI on or off, and the user's answer for their searches as the server
 * keeps it: a sentence goes to the model only once they allowed it, for once or for good. */
function searches(ai: boolean, translate: boolean | null = null) {
  const kept = { translate, posted: [] as (string | null)[] };
  serve({
    'GET /api/actions': () => ({ actions: [], ai }),
    'GET /api/search/ai': () => ({ translate: kept.translate }),
    'PUT /api/search/ai': async (request) => {
      kept.translate = (await request.json()).translate;
    },
    'DELETE /api/search/ai': () => {
      kept.translate = null;
    },
    'POST /api/search/translate': async (request) => {
      const { consent } = await request.json();
      kept.posted.push(consent ?? null);
      if (!consent && kept.translate !== true)
        return Response.json({ error: 'consent_needed' }, { status: 428 });
      return {
        translated: {
          text: 'ponude',
          kind: 'mail',
          from: 'Ana',
          since: '2026-09-01',
          until: '2026-09-30',
        },
      };
    },
    'GET /api/search': () => ({
      filters: [],
      documents: [],
      mail: [],
      events: [],
      tasks: [],
      people: [],
      versions: [],
    }),
    'GET /api/translation': () => ({ languages: null, automatic: false, known: ['hr', 'en'] }),
  });
  return kept;
}

test('with AI off the box searches the words of a sentence', async () => {
  const kept = searches(false);
  const { user, router } = open('/search');
  const box = await screen.findByRole('searchbox', { name: 'Pretraži' });
  await user.type(box, `${SENTENCE}{Enter}`);
  await waitFor(() => expect(router.state.location.search).toMatch(/^\?q=ponude\+koje/));
  expect(kept.posted).toEqual([]);
});

test('a sentence goes to Claude once allowed and comes back as filters, and for good once always allowed', async () => {
  const kept = searches(true);
  const { user, router } = open('/documents');
  await user.type(await screen.findByRole('combobox', { name: 'Pretraži' }), `${SENTENCE}{Enter}`);
  const asked = await screen.findByRole('dialog', { name: 'Slanje teksta modelu Claude' });
  expect(asked.textContent).toContain('Vaši dokumenti i pošta ne odlaze.');
  await user.click(within(asked).getByRole('button', { name: 'Samo ovaj put' }));
  const box = await screen.findByRole('searchbox', { name: 'Pretraži' });
  await waitFor(() => expect(box).toHaveProperty('value', TRANSLATED));

  await user.clear(box);
  await user.type(box, `${SENTENCE}{Enter}`);
  await user.click(
    within(await screen.findByRole('dialog', { name: 'Slanje teksta modelu Claude' })).getByRole(
      'button',
      { name: 'Uvijek za moje pretrage' },
    ),
  );
  await waitFor(() => expect(box).toHaveProperty('value', TRANSLATED));
  expect(kept.translate).toBe(true);

  await router.navigate('/settings/ai');
  const answer = await screen.findByLabelText('Rečenice upisane u tražilicu');
  expect(answer).toHaveProperty('value', 'always');
  await user.selectOptions(answer, 'ask');
  await waitFor(() => expect(kept.translate).toBeNull());
  expect(kept.posted).toEqual([null, 'once', null, null]);
});

test('a sentence searched by its words is kept to its words, and allowed for good in the settings', async () => {
  const kept = searches(true);
  const { user, router } = open('/search');
  const box = await screen.findByRole('searchbox', { name: 'Pretraži' });
  await user.type(box, `${SENTENCE}{Enter}`);
  await user.click(
    within(await screen.findByRole('dialog', { name: 'Slanje teksta modelu Claude' })).getByRole(
      'button',
      { name: 'Samo riječi' },
    ),
  );
  await waitFor(() => expect(kept.translate).toBe(false));
  await waitFor(() => expect(router.state.location.search).toMatch(/^\?q=ponude\+koje/));
  expect(box).toHaveProperty('value', SENTENCE);

  await router.navigate('/settings/ai');
  const answer = await screen.findByLabelText('Rečenice upisane u tražilicu');
  await waitFor(() => expect(answer).toHaveProperty('value', 'words'));
  await user.selectOptions(answer, 'always');
  await waitFor(() => expect(kept.translate).toBe(true));
  expect(kept.posted).toEqual([null]);
});
