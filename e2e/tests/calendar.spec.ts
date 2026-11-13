import { randomBytes } from 'node:crypto';
import { expect, sessions, test } from './fixtures';

test('a calendar is made, an event kept, seen in every view and on Today, repeated and deleted', async ({
  page,
}) => {
  const mine = `Moj ${randomBytes(3).toString('hex')}`;
  await page.goto('/');
  const rail = page.getByRole('navigation', { name: 'Moduli' });
  await rail.getByRole('link', { name: 'Kalendar' }).click();
  await expect(rail.getByRole('link', { name: 'Kalendar' })).toHaveAttribute(
    'aria-current',
    'page',
  );

  const calendars = () => page.getByRole('button', { name: 'Postavke kalendara' }).click();
  await calendars();
  await page.getByRole('button', { name: 'Novi kalendar' }).click();
  const calendar = page.getByRole('dialog', { name: 'Novi kalendar' });
  await calendar.getByLabel('Naziv', { exact: true }).fill(mine);
  await calendar.getByRole('radio', { name: 'Zelena' }).click();
  await calendar.getByRole('button', { name: 'Spremi' }).click();
  await expect(calendar).toBeHidden();
  await expect(page.getByRole('checkbox', { name: mine })).toBeChecked();

  await page.getByRole('button', { name: 'Novi događaj' }).first().click();
  const made = page.getByRole('dialog', { name: 'Novi događaj' });
  await made.getByLabel('Naziv', { exact: true }).fill('Sastanak s Anom');
  await made.getByLabel('Vrijeme početka').fill('10:00');
  await made.getByLabel('Vrijeme završetka').fill('11:00');
  await made.getByLabel('Mjesto').fill('Ured');
  await made.getByRole('button', { name: 'Spremi' }).click();
  await expect(made).toBeHidden();

  const views = page.getByRole('group', { name: 'Prikaz' });
  await expect(page.getByRole('button', { name: /Sastanak s Anom/ })).toBeVisible();
  for (const view of ['Tjedan', 'Dan', 'Popis']) {
    await views.getByRole('button', { name: view, exact: true }).click();
    await expect(views.getByRole('button', { name: view, exact: true })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.getByRole('button', { name: /Sastanak s Anom/ })).toBeVisible();
  }
  await expect(page.getByText('10:00–11:00')).toBeVisible();
  await expect(page.getByText('Ured')).toBeVisible();

  await page.getByRole('button', { name: /Sastanak s Anom/ }).click();
  const edited = page.getByRole('dialog', { name: 'Uredi događaj' });
  await edited.getByLabel('Naziv', { exact: true }).fill('Sastanak s Ivom');
  await edited.getByLabel('Ponavljanje').selectOption({ label: 'Svaki tjedan' });
  await edited.getByRole('button', { name: 'Spremi' }).click();
  await expect(edited).toBeHidden();
  await expect(page.getByRole('button', { name: /Sastanak s Ivom/ })).toHaveCount(5);

  await views.getByRole('button', { name: 'Tjedan' }).click();
  await expect(views.getByRole('button', { name: 'Tjedan' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.getByRole('button', { name: 'Sljedeće' }).click();
  await expect(page.getByRole('button', { name: /Sastanak s Ivom/ })).toBeVisible();
  await page.getByRole('button', { name: /Sastanak s Ivom/ }).click();
  await page
    .getByRole('dialog', { name: 'Uredi događaj' })
    .getByRole('button', { name: 'Obriši' })
    .click();
  const scope = page.getByRole('dialog', { name: 'Obriši ponavljajući događaj' });
  await scope.getByRole('radio', { name: 'Ovaj i sve sljedeće' }).check();
  await scope.getByRole('button', { name: 'Obriši' }).click();
  await expect(scope).toBeHidden();
  await expect(page.getByRole('button', { name: /Sastanak s Ivom/ })).toHaveCount(0);
  await page.getByRole('button', { name: 'Prethodno' }).click();
  await expect(page.getByRole('button', { name: /Sastanak s Ivom/ })).toBeVisible();

  await page.goto('/');
  const today = page.getByRole('region', { name: 'Raspored' });
  await expect(today.getByRole('button', { name: /Sastanak s Ivom/ })).toBeVisible();
  await today.getByRole('button', { name: /Sastanak s Ivom/ }).click();
  await expect(page.getByRole('dialog', { name: 'Uredi događaj' })).toBeVisible();
  await page.keyboard.press('Escape');
  await today.getByRole('link', { name: 'Kalendar' }).click();
  await expect(views.getByRole('button', { name: 'Dan', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  await page.getByRole('button', { name: /Sastanak s Ivom/ }).click();
  await page
    .getByRole('dialog', { name: 'Uredi događaj' })
    .getByRole('button', { name: 'Obriši' })
    .click();
  const whole = page.getByRole('dialog', { name: 'Obriši ponavljajući događaj' });
  await whole.getByRole('radio', { name: 'Sve u nizu' }).check();
  await whole.getByRole('button', { name: 'Obriši' }).click();
  await expect(page.getByRole('button', { name: /Sastanak s Ivom/ })).toHaveCount(0);

  await calendars();
  await page.getByRole('listitem').filter({ hasText: mine }).click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Uredi kalendar' }).click();
  const owned = page.getByRole('dialog', { name: 'Uredi kalendar' });
  await owned.getByRole('button', { name: 'Obriši kalendar' }).click();
  await page
    .getByRole('dialog', { name: 'Obriši kalendar' })
    .getByRole('button', { name: 'Obriši' })
    .click();
  await expect(page.getByRole('checkbox', { name: mine })).toHaveCount(0);
});

test('the event form offers the first times everyone invited is free and takes one', async ({
  page,
  playwright,
  baseURL,
}) => {
  const token = randomBytes(16).toString('hex');
  const colleague = await playwright.request.newContext({
    baseURL,
    extraHTTPHeaders: { 'X-CSRFToken': token },
    storageState: {
      cookies: ['sessionid', 'csrftoken'].map((name) => ({
        name,
        value: name === 'csrftoken' ? token : sessions().colleague,
        domain: new URL(baseURL!).hostname,
        path: '/',
        expires: -1,
        httpOnly: false,
        secure: false,
        sameSite: 'Lax' as const,
      })),
      origins: [],
    },
  });
  const email = (await (await colleague.get('/api/auth/session')).json()).user.email;
  const theirs = await (await colleague.post('/api/calendar', { data: { name: 'Njihov' } })).json();
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const held = await colleague.post(`/api/calendar/events?zone=${zone}`, {
    data: {
      calendar: theirs.id,
      summary: 'Zauzeto jutro',
      start: '2030-06-03T00:00',
      end: '2030-06-03T12:00',
      zone,
    },
  });
  expect(held.status()).toBe(201);
  await colleague.dispose();

  await page.goto('/calendar');
  const mine = `Moj ${token.slice(0, 6)}`;
  await page.getByRole('button', { name: 'Postavke kalendara' }).click();
  await page.getByRole('button', { name: 'Novi kalendar' }).click();
  const calendar = page.getByRole('dialog', { name: 'Novi kalendar' });
  await calendar.getByLabel('Naziv', { exact: true }).fill(mine);
  await calendar.getByRole('button', { name: 'Spremi' }).click();
  await expect(calendar).toBeHidden();

  await page.getByRole('button', { name: 'Novi događaj' }).first().click();
  const made = page.getByRole('dialog', { name: 'Novi događaj' });
  await made.getByLabel('Naziv', { exact: true }).fill('Dogovor');
  await made.getByLabel('Početak', { exact: true }).fill('2030-06-03');
  await made.getByLabel('Završetak', { exact: true }).fill('2030-06-03');
  await made.getByLabel('Vrijeme početka').fill('09:00');
  await made.getByLabel('Vrijeme završetka').fill('10:00');
  await made.getByLabel('Pozvani').fill(email);
  await made.getByLabel('Pozvani').press('Enter');
  await expect(made.getByText('U to vrijeme zauzeti')).toBeVisible();
  const offers = made.getByRole('region', { name: 'Slobodni termini za sve' });
  await offers.getByRole('button').first().click();
  await expect(made.getByLabel('Vrijeme početka')).toHaveValue('12:00');
  await expect(made.getByLabel('Vrijeme završetka')).toHaveValue('13:00');
  await expect(made.getByText('U to vrijeme zauzeti')).toBeHidden();
  await expect(offers).toBeHidden();
});
