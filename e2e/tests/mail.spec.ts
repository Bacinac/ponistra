import type { Locator } from '@playwright/test';
import { expect, test } from './fixtures';

test('an account is connected through its server settings, its mail kept once it is removed', async ({
  page,
  problems,
}) => {
  test.slow();
  await page.goto('/');
  const rail = page.getByRole('navigation', { name: 'Moduli' });
  await rail.getByRole('link', { name: 'Pošta' }).click();
  await expect(rail.getByRole('link', { name: 'Pošta' })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByText('Nijedan račun e-pošte nije povezan.')).toBeVisible();

  await page.getByRole('button', { name: 'Poveži račun' }).click();
  const dialog = page.getByRole('dialog', { name: 'Povezivanje računa e-pošte' });
  await dialog.getByLabel('Adresa e-pošte').fill('ime@gmail.com');
  await dialog.getByLabel('Adresa e-pošte').press('Tab');
  await expect(dialog.getByLabel('Lozinka aplikacije')).toBeFocused();
  await expect(dialog.getByRole('link', { name: 'Izradite lozinku aplikacije' })).toHaveAttribute(
    'href',
    'https://myaccount.google.com/apppasswords',
  );
  await dialog.getByLabel('Adresa e-pošte').fill('mox@localhost');
  await expect(dialog.getByRole('link', { name: 'Izradite lozinku aplikacije' })).toBeHidden();
  await dialog.getByLabel('Lozinka').fill('moxmoxmox');
  await dialog.getByRole('button', { name: 'Poveži račun' }).click();
  await expect(
    dialog.getByText('Dolazni poslužitelj nije dostupan; provjerite poslužitelj i priključak.'),
  ).toBeVisible({ timeout: 40_000 });
  const refused = problems.filter((problem) => problem.includes('status of 400'));
  expect(refused).toHaveLength(1);
  problems.splice(0, problems.length, ...problems.filter((problem) => !refused.includes(problem)));
  await expect(dialog.getByLabel('Korisničko ime')).toHaveValue('mox@localhost');
  const incoming = dialog.getByRole('group', { name: 'Dolazna pošta (IMAP)' });
  await expect(incoming.getByLabel('Poslužitelj')).toHaveValue('imap.localhost');
  await expect(incoming.getByRole('option', { name: 'Bez šifriranja' })).toBeDisabled();
  for (const [name, port] of [
    ['Dolazna pošta (IMAP)', '1143'],
    ['Odlazna pošta (SMTP)', '1587'],
  ]) {
    const server = dialog.getByRole('group', { name });
    await server.getByLabel('Poslužitelj').fill('mox');
    await server.getByLabel('Šifriranje').selectOption('none');
    await server.getByLabel('Priključak').fill(port);
  }
  await dialog.getByRole('button', { name: 'Poveži račun' }).click();
  await expect(dialog).toBeHidden();

  const accounts = page.getByRole('navigation', { name: 'Računi e-pošte' });
  const account = accounts.getByRole('region', { name: 'mox@localhost' });
  await expect(page.getByRole('heading', { level: 1, name: 'Pristigla pošta' })).toBeVisible();
  await expect(accounts.getByRole('link')).toHaveText([
    'Pristigla pošta',
    'Omiljeno',
    'Skice',
    'Poslano',
    'Arhiva',
    'Neželjena pošta',
    'Smeće',
    'mox@localhost',
  ]);
  await expect(accounts.getByRole('link', { name: 'Pristigla pošta' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await expect(page.getByText('U ovoj mapi nema poruka.')).toBeVisible();
  await accounts.getByRole('link', { name: 'Poslano' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Poslano' })).toBeVisible();

  await page.getByRole('button', { name: 'Nova poruka' }).click();
  const compose = page.getByRole('dialog', { name: 'Nova poruka' });
  await expect(compose.getByLabel('Šalje')).toHaveValue(/\d+/);
  await expect(compose.getByLabel('Šalje').getByRole('option')).toHaveText(['mox@localhost']);
  await compose.getByRole('button', { name: 'Pošalji', exact: true }).click();
  await expect(compose.getByText('Upišite barem jednog primatelja.')).toBeVisible();
  const empty = problems.filter((problem) => problem.includes('status of 400'));
  expect(empty).toHaveLength(1);
  problems.splice(0, problems.length, ...problems.filter((problem) => !empty.includes(problem)));
  const subject = `Proba ${Date.now()}`;
  await compose.getByLabel('Za').fill('Ana Kovač <ana@example.com>');
  await compose.getByLabel('Predmet').fill(subject);
  await compose.getByLabel('Poruka').fill('Pozdrav iz ');
  await compose.getByRole('button', { name: 'Podebljano' }).click();
  await compose.getByLabel('Poruka').pressSequentially('Ponistre.');
  await expect(compose.getByLabel('Poruka').locator('strong')).toHaveText('Ponistre.');
  await compose.getByRole('button', { name: 'Pošalji', exact: true }).click();
  await expect(compose).toBeHidden({ timeout: 20_000 });
  const order = page.getByRole('button', { name: /^Poredak/ });
  const sent = page
    .getByRole('list', { name: 'Poslano' })
    .getByRole('listitem')
    .filter({ hasText: subject });
  await expect(sent).toBeVisible();
  await expect(order).toBeHidden();
  await sent.getByRole('link').hover();
  await page.mouse.down();
  await expect(page.getByText('Odabrano: 1')).toBeVisible();
  await page.mouse.up();
  await expect(order).toContainText('Datum, najnovije prvo');
  await order.click();
  await page.getByRole('menuitemcheckbox', { name: 'Primatelj' }).click();
  await expect(order).toContainText('Primatelj, A → Ž');
  await order.click();
  await page.getByRole('menuitemcheckbox', { name: 'Ž → A' }).click();
  await expect(order).toContainText('Primatelj, Ž → A');
  await expect(page.getByRole('link', { name: new RegExp(subject) })).toBeVisible();
  await order.click();
  await page.getByRole('menuitemcheckbox', { name: 'Datum' }).click();
  await expect(order).toContainText('Datum, najnovije prvo');
  await page.getByRole('button', { name: 'Odabir' }).click();
  await page.getByRole('menuitem', { name: 'Poništi odabir' }).click();
  await expect(order).toBeHidden();
  await page.getByRole('link', { name: new RegExp(subject) }).click();
  await expect(page.getByRole('article', { name: subject })).toBeVisible();

  await page.getByRole('button', { name: 'Dodaj u omiljeno' }).click();
  await accounts.getByRole('link', { name: 'Omiljeno' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Omiljeno' })).toBeVisible();
  const favourite = page
    .getByRole('list', { name: 'Omiljeno' })
    .getByRole('listitem')
    .filter({ hasText: subject });
  await favourite.getByRole('link').click();
  await expect(page.getByRole('article', { name: subject })).toBeVisible();
  await page.getByRole('button', { name: 'Ukloni iz omiljenog' }).click();
  await expect(favourite).toBeHidden();
  await accounts.getByRole('link', { name: 'Poslano' }).click();
  await page.getByRole('link', { name: new RegExp(subject) }).click();
  await expect(page.getByRole('article', { name: subject })).toBeVisible();

  await page.getByRole('button', { name: 'Odgovori', exact: true }).click();
  const reply = page.getByRole('dialog', { name: 'Nova poruka' });
  await expect(reply.getByTitle('Ana Kovač <ana@example.com>')).toBeVisible();
  await expect(reply.getByLabel('Predmet')).toHaveValue(`Re: ${subject}`);
  await expect(reply.getByLabel('Poruka')).toBeFocused();
  await reply.getByRole('button', { name: 'Prikaži citiranu poruku' }).click();
  await expect(
    reply.locator('iframe').contentFrame().getByText('Pozdrav iz Ponistre.'),
  ).toBeVisible();
  await reply.getByLabel('Poruka').press('ControlOrMeta+Home');
  await reply.getByLabel('Poruka').pressSequentially('Hvala.');
  await reply.getByRole('button', { name: 'Odbaci' }).click();
  const discard = page.getByRole('alertdialog', { name: 'Odbaciti poruku?' });
  await discard.getByRole('button', { name: 'Odbaci' }).click();
  await expect(reply).toBeHidden();

  const reacted = page.getByRole('article', { name: subject });
  await reacted.getByRole('button', { name: 'Reagiraj' }).click();
  await page.getByRole('menuitem', { name: '👍' }).click();
  const thumbs = reacted
    .getByRole('list', { name: 'Reakcije' })
    .getByRole('button', { name: /👍/ });
  await expect(thumbs).toHaveAttribute('aria-pressed', 'true');
  await expect(thumbs).toBeDisabled();

  const search = page.getByRole('combobox', { name: 'Pretraži' });
  await search.fill(`${subject} vrsta:pošta`);
  await expect(page.getByRole('listitem').filter({ hasText: 'Vrsta:' })).toContainText('Pošta');
  const found = page.getByRole('option', { name: new RegExp(subject) });
  await expect(found).toContainText('Ana Kovač');
  await search.press('ArrowDown');
  await search.press('Enter');
  await expect(page.getByRole('article', { name: subject })).toBeVisible();

  const article = page.getByRole('article', { name: subject });
  const unseen = page.getByRole('link', { name: new RegExp(`^Nepročitano: .*${subject}`) });
  await article.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Označi kao nepročitano' }).click();
  await expect(unseen).toBeVisible();
  await page.getByRole('banner').getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Označi sve kao pročitano' }).click();
  await expect(unseen).toBeHidden();
  await article.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Označi kao nepročitano' }).click();
  await expect(unseen).toBeVisible();
  await accounts.getByRole('link', { name: 'Poslano' }).click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Označi sve kao pročitano' }).click();
  await expect(unseen).toBeHidden();
  await page.getByRole('banner').getByRole('button', { name: 'Radnje' }).click();
  await expect(page.getByRole('menuitem', { name: 'Označi sve kao pročitano' })).toBeDisabled();
  await page.keyboard.press('Escape');

  const listed = page.getByRole('link', { name: new RegExp(subject) });
  const shared = account.getByRole('button', { name: 'Prikaži u zajedničkoj pošti' });
  const together = page.getByRole('menuitemcheckbox', { name: 'Prikaži u zajedničkoj pošti' });
  await expect(shared).toHaveAttribute('aria-pressed', 'true');
  await shared.click();
  await expect(shared).toHaveAttribute('aria-pressed', 'false');
  await expect(listed).toBeHidden();
  await account.getByRole('link', { name: /^mox@localhost/ }).click();
  await listed.click();
  await expect(page).toHaveURL(/\/mail\/\d+\/\d+\?account=\d+$/);
  await page.getByRole('link', { name: 'Prikaži sve račune' }).click();
  await expect(listed).toBeHidden();
  await account.getByRole('link', { name: /^mox@localhost/ }).click();
  await expect(listed).toBeVisible();
  await expect(accounts.getByRole('link', { name: 'Poslano' })).not.toHaveAttribute('aria-current');
  await accounts.getByRole('link', { name: 'Poslano' }).click();
  await expect(page).toHaveURL(/\/mail\/\d+$/);
  await expect(listed).toBeHidden();
  await account.getByRole('heading').click({ button: 'right' });
  await expect(together).not.toBeChecked();
  await together.click();
  await expect(shared).toHaveAttribute('aria-pressed', 'true');

  await page.evaluate(async () => {
    const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
    const response = await fetch('/api/mail/images', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify({ domain: 'example.com', shown: false }),
    });
    if (!response.ok) throw new Error(`POST /api/mail/images: ${response.status}`);
  });
  await page.goto('/settings/senders');
  const decided = page.getByRole('region', { name: 'Slike po domeni' });
  await expect(page.getByText('Još nema nijednog pošiljatelja.')).toBeVisible();
  await expect(decided.getByRole('listitem')).toHaveText(['example.comIzostavljaju se']);
  await decided
    .getByRole('button', { name: 'Ponovno pitaj za slike s domene example.com' })
    .click();
  await expect(decided.getByText('Još nema nijedne domene.')).toBeVisible();
  await page.goBack();

  // A long press opens the account's menu where it is, and leaves its link unfollowed.
  const before = page.url();
  await account.getByRole('heading').hover();
  await page.mouse.down();
  await expect(page.getByRole('menuitem', { name: 'Potpis' })).toBeVisible();
  await page.mouse.up();
  await expect(page).toHaveURL(before);
  await page.getByRole('menuitem', { name: 'Potpis' }).click();
  const signing = page.getByRole('dialog', { name: /^Potpis/ });
  await signing.getByLabel('Potpis').fill('Ivo Proba');
  await signing.getByLabel('Potpis').press('ControlOrMeta+a');
  await signing.getByRole('button', { name: 'Podebljano' }).click();
  await signing.getByRole('button', { name: 'Spremi' }).click();
  await expect(signing).toBeHidden();

  const other = `Druga ${Date.now()}`;
  await page.getByRole('button', { name: 'Nova poruka' }).click();
  await expect(compose.getByLabel('Poruka').locator('strong')).toHaveText('Ivo Proba');
  await compose.getByLabel('Za').fill('kov');
  await compose.getByRole('option', { name: /ana@example\.com/ }).click();
  await expect(compose.getByTitle('Ana Kovač <ana@example.com>')).toBeVisible();
  await expect(compose.getByLabel('Za')).toHaveValue('');
  await compose.getByLabel('Predmet').fill(other);
  await compose.getByLabel('Poruka').fill('Još jedna.');
  await compose.getByRole('button', { name: 'Pošalji', exact: true }).click();
  await expect(compose).toBeHidden({ timeout: 20_000 });
  const row = (folder: string, name: string) =>
    page.getByRole('list', { name: folder }).getByRole('listitem').filter({ hasText: name });
  const press = async (found: Locator) => {
    await found.getByRole('link').hover();
    await page.mouse.down();
    await expect(page.getByText('Odabrano: 1')).toBeVisible();
    await page.mouse.up();
  };
  const both = async () => {
    await press(row('Poslano', subject));
    await row('Poslano', other)
      .getByRole('link')
      .click({ modifiers: ['Shift'] });
    await expect(page.getByText('Odabrano: 2')).toBeVisible();
  };
  await expect(page.getByRole('checkbox', { name: 'Odaberi sve' })).toBeHidden();
  await row('Poslano', other).click({ button: 'right' });
  await expect(page.getByRole('menuitem', { name: 'Arhiviraj' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('menu')).toBeHidden();
  await expect(row('Poslano', other).getByRole('link')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByText(/^Odabrano: /)).toBeHidden();
  await both();
  await expect(page.getByRole('article')).toBeHidden();
  await page.getByRole('button', { name: 'Označi kao nepročitano' }).click();
  for (const name of [subject, other]) {
    await expect(row('Poslano', name).getByRole('link', { name: /^Nepročitano: / })).toBeVisible();
  }
  await expect(page.getByText(/^Odabrano: /)).toBeHidden();
  await both();
  await page.getByRole('button', { name: 'Arhiviraj' }).click();
  await expect(row('Poslano', other)).toBeHidden();
  await accounts.getByRole('link', { name: 'Arhiva' }).click();
  await press(row('Arhiva', other));
  await page.getByRole('button', { name: 'Odabir' }).click();
  await page.getByRole('menuitem', { name: 'Odaberi sve (2)' }).click();
  await expect(page.getByText('Odabrano: 2')).toBeVisible();
  await page.getByRole('button', { name: 'Premjesti u', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Poslano', exact: true }).click();
  await expect(page.getByText('U ovoj mapi nema poruka.')).toBeVisible();
  await accounts.getByRole('link', { name: 'Poslano' }).click();

  await row('Poslano', other).getByRole('link').click();
  await page.getByRole('article').getByRole('button', { name: 'Čekaj odgovor' }).click();
  await page
    .getByRole('dialog', { name: 'Do kada čekati odgovor?' })
    .getByRole('button', { name: /Sutra ujutro/ })
    .click();
  await expect(page.getByText(/^Čeka se odgovor do /)).toBeVisible();
  await expect(row('Poslano', other).getByRole('img', { name: 'Čekaj odgovor' })).toBeVisible();
  await page.getByRole('button', { name: 'Ne čekaj odgovor' }).click();
  await expect(page.getByText(/^Čeka se odgovor do /)).toBeHidden();

  await press(row('Poslano', subject));
  await page.getByRole('button', { name: 'Premjesti u', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Pristigla pošta', exact: true }).click();
  await accounts.getByRole('link', { name: 'Pristigla pošta' }).click();

  await row('Pristigla pošta', subject).getByRole('link').click();
  await page.getByRole('article').getByRole('button', { name: 'Odgodi' }).click();
  const when = page.getByRole('dialog', { name: 'Do kada odgoditi poruku?' });
  await when.getByRole('button', { name: /Sutra ujutro/ }).click();
  await expect(row('Pristigla pošta', subject)).toBeHidden();
  await accounts.getByRole('link', { name: 'Odgođeno' }).click();
  await row('Odgođeno', subject).getByRole('link').click();
  await expect(page.getByText(/^Odgođeno do /)).toBeVisible();
  await page.getByRole('article').getByRole('button', { name: 'Vrati u pristiglu poštu' }).click();
  await accounts.getByRole('link', { name: 'Pristigla pošta' }).click();
  await expect(row('Pristigla pošta', subject)).toBeVisible();
  await row('Pristigla pošta', subject).getByRole('link').click();
  await page
    .getByRole('article', { name: subject })
    .getByRole('button', { name: 'Radnje' })
    .click();
  await page.getByRole('menuitem', { name: 'Uvijek premjesti u mapu…' }).click();
  const ruling = page.getByRole('dialog', { name: 'Uvijek premjesti u mapu' });
  await expect(ruling.getByRole('radio')).toHaveCount(1);
  await expect(ruling.getByRole('radio', { name: 'mox@localhost' })).toBeChecked();
  await expect(ruling.getByRole('button', { name: 'Spremi' })).toBeDisabled();
  await ruling.getByLabel('Mapa').selectOption({ label: 'Arhiva' });
  await ruling.getByRole('button', { name: 'Spremi' }).click();
  await expect(ruling).toBeHidden();
  await expect(page.getByRole('article', { name: subject })).toBeHidden();
  await expect(row('Pristigla pošta', subject)).toBeHidden();
  await accounts.getByRole('link', { name: 'Arhiva' }).click();
  await press(row('Arhiva', subject));
  await page.getByRole('button', { name: 'Blokiraj pošiljatelje' }).click();
  await expect(row('Arhiva', subject)).toBeHidden();
  await page.goto('/settings/senders');
  await expect(
    page.getByRole('list', { name: 'Blokirani i premješteni' }).getByRole('listitem'),
  ).toHaveText(['mox@localhostNeželjena pošta']);
  await page.goBack();
  await accounts.getByRole('link', { name: 'Neželjena pošta' }).click();
  await row('Neželjena pošta', subject).getByRole('link').click();
  await page
    .getByRole('article', { name: subject })
    .getByRole('button', { name: 'Radnje' })
    .click();
  await page.getByRole('menuitem', { name: 'Nije neželjena pošta' }).click();
  await expect(row('Neželjena pošta', subject)).toBeHidden();
  await accounts.getByRole('link', { name: 'Pristigla pošta' }).click();
  await press(row('Pristigla pošta', subject));
  await page.getByRole('button', { name: 'Premjesti u', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Poslano', exact: true }).click();
  await expect(row('Pristigla pošta', subject)).toBeHidden();
  await page.goto('/settings/senders');
  await expect(page.getByText('Još nema nijednog pošiljatelja.')).toBeVisible();
  await page.goBack();
  await accounts.getByRole('link', { name: 'Poslano' }).click();

  await listed.click();
  await page.getByRole('button', { name: 'Premjesti u smeće' }).click();
  await expect(page.getByRole('article', { name: subject })).toBeHidden();
  await expect(page.getByRole('link', { name: new RegExp(subject) })).toBeHidden();
  await row('Poslano', other).getByRole('link').focus();
  await page.keyboard.press(' ');
  await expect(page.getByText('Odabrano: 1')).toBeVisible();
  await page.keyboard.press('Delete');
  await expect(row('Poslano', other)).toBeHidden();

  const invited = `Kolegij ${Date.now()}`;
  const invitation = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//PONISTRA e2e//EN',
    'METHOD:REQUEST',
    'BEGIN:VEVENT',
    `UID:e2e-${Date.now()}@example.org`,
    'DTSTAMP:20261026T100000Z',
    'DTSTART;TZID=Europe/Zagreb:20270302T090000',
    'DTEND;TZID=Europe/Zagreb:20270302T100000',
    `SUMMARY:${invited}`,
    'ORGANIZER;CN=Ana Kovač:mailto:ana@example.org',
    'ATTENDEE;CN=Ana Kovač;PARTSTAT=ACCEPTED:mailto:ana@example.org',
    'ATTENDEE;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:mox@localhost',
    'END:VEVENT',
    'END:VCALENDAR',
    '',
  ].join('\r\n');
  await page.getByRole('button', { name: 'Nova poruka' }).click();
  await compose.getByLabel('Za').fill('Ana Kovač <ana@example.org>');
  await compose.getByLabel('Predmet').fill(`Poziv: ${invited}`);
  await compose.getByLabel('Poruka').fill('Pozivnica u privitku.');
  await compose.locator('input[type="file"][accept=""]').setInputFiles({
    name: 'poziv.ics',
    mimeType: 'text/calendar',
    buffer: Buffer.from(invitation, 'utf-8'),
  });
  await expect(compose.getByText('poziv.ics')).toBeVisible();
  await compose.getByRole('button', { name: 'Pošalji', exact: true }).click();
  await expect(compose).toBeHidden({ timeout: 20_000 });
  await row('Poslano', `Poziv: ${invited}`).getByRole('link').click();
  const meeting = page.getByRole('region', { name: 'Poziv na sastanak' });
  await expect(meeting).toContainText(invited);
  await expect(meeting).toContainText('Ana Kovač');
  await expect(meeting.getByRole('button', { name: 'Prihvati' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  await meeting.getByRole('button', { name: 'Prihvati' }).click();
  await expect(meeting.getByRole('button', { name: 'Prihvati' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await meeting.getByRole('link', { name: 'Otvori u kalendaru' }).click();
  const views = page.getByRole('group', { name: 'Prikaz' });
  await expect(views.getByRole('button', { name: 'Dan', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.getByRole('button', { name: new RegExp(invited) }).click();
  const held = page.getByRole('dialog', { name: 'Uredi događaj' });
  await expect(held.getByLabel('Naziv', { exact: true })).toHaveValue(invited);
  await expect(
    held.getByRole('group', { name: 'Vaš odgovor' }).getByRole('button', { name: 'Prihvati' }),
  ).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');
  await expect(held).toBeHidden();

  const called = `Sastanak s Anom ${Date.now()}`;
  await page.getByRole('button', { name: 'Novi događaj' }).first().click();
  const calling = page.getByRole('dialog', { name: 'Novi događaj' });
  await calling.getByLabel('Naziv', { exact: true }).fill(called);
  await calling.getByLabel('Pozvani').fill('Ana Kovač <ana@example.org>');
  await calling.getByLabel('Pozvani').press('Enter');
  await expect(
    calling.getByText('Pozvanima stiže pozivnica e-poštom', { exact: false }),
  ).toBeVisible();
  await calling.getByRole('button', { name: 'Spremi' }).click();
  await expect(calling).toBeHidden({ timeout: 20_000 });
  await page.getByRole('button', { name: new RegExp(called) }).click();
  const calledHeld = page.getByRole('dialog', { name: 'Uredi događaj' });
  await expect(calledHeld.getByText('Organizator: mox@localhost')).toBeVisible();
  await expect(calledHeld.getByText('bez odgovora')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(calledHeld).toBeHidden();

  await page
    .getByRole('navigation', { name: 'Moduli' })
    .getByRole('link', { name: 'Pošta' })
    .click();
  await expect(account).toBeVisible();
  await accounts.getByRole('link', { name: 'Poslano' }).click();
  await expect(row('Poslano', `Poziv: ${called}`)).toBeVisible();
  await expect(row('Poslano', `Prihvaćeno: ${invited}`)).toBeVisible();
  await press(row('Poslano', `Poziv: ${invited}`));
  await row('Poslano', `Poziv: ${called}`)
    .getByRole('link')
    .click({ modifiers: ['Shift'] });
  await expect(page.getByText('Odabrano: 3')).toBeVisible();
  await page.keyboard.press('Delete');
  await expect(row('Poslano', `Poziv: ${invited}`)).toBeHidden();
  await accounts.getByRole('link', { name: 'Smeće' }).click();
  await press(row('Smeće', `Poziv: ${invited}`));
  await row('Smeće', `Poziv: ${called}`)
    .getByRole('link')
    .click({ modifiers: ['Shift'] });
  await expect(page.getByText('Odabrano: 3')).toBeVisible();
  await page.getByRole('button', { name: 'Trajno izbriši' }).click();
  await page
    .getByRole('alertdialog', { name: 'Trajno izbrisati odabrane poruke?' })
    .getByRole('button', { name: 'Trajno izbriši' })
    .click();
  await expect(row('Smeće', `Poziv: ${invited}`)).toBeHidden();

  await account.getByRole('heading').click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Postavke računa' }).click();
  const settings = page.getByRole('dialog', { name: 'Postavke računa' });
  await expect(settings.getByLabel('Adresa e-pošte')).toBeDisabled();
  await expect(settings.getByText('Ostavite prazno da ostane dosadašnja lozinka.')).toBeVisible();
  await settings.getByRole('button', { name: 'Postavke poslužitelja' }).click();
  const outgoing = settings.getByRole('group', { name: 'Odlazna pošta (SMTP)' });
  const protocol = settings.getByLabel('Vrsta poslužitelja');
  await expect(protocol).toHaveValue('imap');
  await protocol.selectOption({ label: 'ActiveSync (Exchange, HCL Traveler)' });
  await expect(settings.getByLabel('ActiveSync poslužitelj')).toHaveValue('');
  await expect(outgoing).toBeHidden();
  await protocol.selectOption({ label: 'IMAP i SMTP' });
  await expect(outgoing.getByLabel('Priključak')).toHaveValue('1587');
  await settings.getByRole('button', { name: 'Spremi' }).click();
  await expect(settings).toBeHidden();

  await account.getByRole('heading').click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Preimenuj' }).click();
  const renaming = page.getByRole('dialog', { name: 'Preimenuj' });
  await renaming.getByLabel('Naziv').fill('Testni račun');
  await renaming.getByRole('button', { name: 'Spremi' }).click();
  const named = accounts.getByRole('region', { name: 'Testni račun' });
  await expect(named.getByText('Testni račun')).toHaveAttribute('title', 'mox@localhost');

  await named.getByRole('heading').click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Ukloni račun' }).click();
  const removal = page.getByRole('alertdialog', { name: 'Ukloniti račun?' });
  await expect(removal.getByText('Testni račun')).toBeVisible();
  await removal.getByRole('button', { name: 'Ukloni račun' }).click();
  await expect(named).toBeHidden();
  await expect(page.getByRole('button', { name: 'Nova poruka' })).toBeHidden();
  await accounts.getByRole('link', { name: 'Smeće' }).click();
  await page.getByRole('link', { name: new RegExp(subject) }).click();
  await page.getByRole('button', { name: 'Trajno izbriši' }).click();
  const forGood = page.getByRole('alertdialog', { name: 'Trajno izbrisati poruku?' });
  await forGood.getByRole('button', { name: 'Trajno izbriši' }).click();
  await expect(row('Smeće', subject)).toBeHidden();
  await press(row('Smeće', other));
  await page.getByRole('button', { name: 'Trajno izbriši' }).click();
  const chosenForGood = page.getByRole('alertdialog', {
    name: 'Trajno izbrisati odabrane poruke?',
  });
  await chosenForGood.getByRole('button', { name: 'Trajno izbriši' }).click();
  await expect(page.getByText('Nijedan račun e-pošte nije povezan.')).toBeVisible();
  await expect(page).toHaveURL(/\/mail$/);
});

test('an account signs in through its provider once an administrator has entered the client', async ({
  page,
}) => {
  await page.route('**/api/auth/session', async (route) => {
    const response = await route.fetch();
    const { user } = await response.json();
    await route.fulfill({ response, json: { user: { ...user, is_admin: true } } });
  });
  const redirect = (provider: string) => `https://ponistra.example/api/oauth/${provider}`;
  const clients = ['google', 'microsoft'].map((provider) => ({
    provider,
    redirect: redirect(provider),
    client_id: '',
    hint: '',
    lost: false,
    expires: null as string | null,
    changed_at: null as string | null,
  }));
  let entered: unknown;
  await page.route('**/api/mail/clients', (route) => route.fulfill({ json: { clients } }));
  await page.route('**/api/mail/setting', (route) =>
    route.fulfill({ json: { opened: true, changed_by: null, changed_at: null } }),
  );
  await page.route('**/api/mail/clients/microsoft', async (route) => {
    entered = route.request().postDataJSON();
    Object.assign(clients[1], {
      client_id: 'ponistra-id',
      hint: 'cret',
      expires: '2028-10-24',
      changed_at: '2026-10-24T12:00:00Z',
    });
    await route.fulfill({ json: clients[1] });
  });
  await page.route('**/api/mail/accounts', async (route) => {
    const response = await route.fetch();
    const providers = clients[1].hint ? { microsoft: 'outlook.office365.com' } : {};
    await route.fulfill({ response, json: { ...(await response.json()), providers } });
  });
  await page.route('**/api/mail/oauth/microsoft', (route) =>
    route.fulfill({ json: { url: '/mail?oauth=oauth_login' } }),
  );

  await page.goto('/mail?oauth=oauth_denied');
  const dialog = page.getByRole('dialog', { name: 'Povezivanje računa e-pošte' });
  await expect(
    dialog.getByText('Prijava kod pružatelja je otkazana ili pristup nije odobren.'),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/mail$/);
  await expect(dialog.getByRole('button', { name: 'Poveži s Microsoftom' })).toBeHidden();
  await dialog.getByRole('link', { name: 'Pošta', exact: true }).click();
  await expect(
    page.getByLabel('Pošiljatelj poruke vidi koje su je kolege otvorile i kada'),
  ).toBeChecked();

  const microsoft = page
    .locator('form')
    .filter({ has: page.getByRole('heading', { name: 'Microsoft' }) });
  await expect(microsoft.getByLabel('Adresa za povratak (redirect URI)')).toHaveValue(
    redirect('microsoft'),
  );
  await microsoft.getByLabel('ID klijenta').fill('ponistra-id');
  await microsoft.getByLabel('Tajna klijenta').fill('s3cret');
  await microsoft.getByLabel('Tajna vrijedi do').fill('2028-10-24');
  await microsoft.getByRole('button', { name: 'Spremi' }).click();
  await expect(microsoft.getByText('Tajna je spremljena i završava na …cret')).toBeVisible();
  expect(entered).toEqual({ client_id: 'ponistra-id', secret: 's3cret', expires: '2028-10-24' });
  await expect(microsoft.getByLabel('Tajna klijenta')).toHaveValue('');

  await page
    .getByRole('navigation', { name: 'Postavke' })
    .getByRole('link', { name: 'Računi e-pošte' })
    .click();
  await page.getByRole('button', { name: 'Poveži račun' }).click();
  await expect(dialog.getByRole('button', { name: 'Poveži s Googleom' })).toBeHidden();
  await dialog.getByLabel('Adresa e-pošte').fill('ime@outlook.com');
  await dialog.getByLabel('Adresa e-pošte').blur();
  await expect(
    dialog.getByText('Microsoft za ovu adresu ne prima lozinku', { exact: false }),
  ).toBeVisible();
  await expect(dialog.getByLabel('Lozinka')).toBeHidden();
  await expect(dialog.getByRole('button', { name: 'Poveži račun' })).toBeHidden();
  await dialog.getByRole('button', { name: 'Poveži s Microsoftom' }).click();
  await expect(
    dialog.getByText('Pružatelj više ne prihvaća prijavu ovog računa', { exact: false }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/mail$/);
  await page.unrouteAll({ behavior: 'ignoreErrors' });
});
