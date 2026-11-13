import { expect, test } from './fixtures';

const ROOM = 'Dvorana (e2e)';

test('a room is booked by the event, shown among the events and refused to a second one at that time', async ({
  page,
}) => {
  const stamp = Date.now().toString(36);
  const mine = `Moj ${stamp}`;
  await page.goto('/calendar/day');
  await page.getByRole('button', { name: 'Postavke kalendara' }).click();
  await page.getByRole('button', { name: 'Novi kalendar' }).click();
  const calendar = page.getByRole('dialog', { name: 'Novi kalendar' });
  await calendar.getByLabel('Naziv', { exact: true }).fill(mine);
  await calendar.getByRole('button', { name: 'Spremi' }).click();
  await expect(calendar).toBeHidden();

  const title = `Kolegij ${stamp}`;
  await page.getByRole('button', { name: 'Novi događaj' }).first().click();
  const made = page.getByRole('dialog', { name: 'Novi događaj' });
  await made.getByLabel('Naziv', { exact: true }).fill(title);
  await made.getByLabel('Vrijeme početka').fill('10:00');
  await made.getByLabel('Vrijeme završetka').fill('11:00');
  const room = made.getByRole('group', { name: 'Sobe i resursi' }).getByRole('checkbox', {
    name: new RegExp(ROOM.replace(/[()]/g, '\\$&')),
  });
  await expect(room).toBeEnabled();
  await room.check();
  await made.getByRole('button', { name: 'Spremi' }).click();
  await expect(made).toBeHidden();
  await expect(page.getByRole('button', { name: new RegExp(title) })).toBeVisible();

  const panel = page.getByRole('region', { name: 'Sobe i resursi' });
  await panel.getByRole('checkbox', { name: ROOM }).check();
  await expect(page.getByRole('button', { name: `${ROOM}: ${title}` })).toBeVisible();
  await page.getByRole('button', { name: `${ROOM}: ${title}` }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  await page.getByRole('button', { name: 'Novi događaj' }).first().click();
  const second = page.getByRole('dialog', { name: 'Novi događaj' });
  await second.getByLabel('Naziv', { exact: true }).fill(`Prezentacija ${stamp}`);
  await second.getByLabel('Vrijeme početka').fill('10:30');
  await second.getByLabel('Vrijeme završetka').fill('11:30');
  const taken = second.getByRole('group', { name: 'Sobe i resursi' }).getByRole('checkbox', {
    name: new RegExp(ROOM.replace(/[()]/g, '\\$&')),
  });
  await expect(taken).toBeDisabled();
  await expect(second.getByText('(zauzeto)')).toBeVisible();
  await second.getByLabel('Vrijeme početka').fill('11:00');
  await second.getByLabel('Vrijeme završetka').fill('12:00');
  await expect(taken).toBeEnabled();
  await page.keyboard.press('Escape');
  await expect(second).toBeHidden();

  await page
    .getByRole('button', { name: new RegExp(`^(?!${ROOM.replace(/[()]/g, '\\$&')}).*${title}`) })
    .click();
  const edited = page.getByRole('dialog', { name: 'Uredi događaj' });
  await expect(
    edited.getByRole('group', { name: 'Sobe i resursi' }).getByRole('checkbox', {
      name: new RegExp(ROOM.replace(/[()]/g, '\\$&')),
    }),
  ).toBeChecked();
  await edited.getByRole('button', { name: 'Obriši' }).click();
  await expect(edited).toBeHidden();
  await expect(page.getByRole('button', { name: new RegExp(title) })).toHaveCount(0);
  await panel.getByRole('checkbox', { name: ROOM }).uncheck();

  await page.getByRole('listitem').filter({ hasText: mine }).click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Uredi kalendar' }).click();
  await page
    .getByRole('dialog', { name: 'Uredi kalendar' })
    .getByRole('button', { name: 'Obriši kalendar' })
    .click();
  await page
    .getByRole('dialog', { name: 'Obriši kalendar' })
    .getByRole('button', { name: 'Obriši' })
    .click();
  await expect(page.getByRole('checkbox', { name: mine })).toHaveCount(0);
});
