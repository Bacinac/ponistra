import { expect, test, type Page } from './fixtures';

test.use({ administrator: true });

const STACK = `services:
  app:
    image: ponistra/test:1
    pull_policy: never
    command: ["sh", "-c", "echo zdravo; exec sleep 3600"]
    stop_grace_period: 1s
`;

async function addLocation(page: Page, name: string, path: string) {
  await page.goto('/settings/locations');
  await page.getByRole('button', { name: 'Dodaj lokaciju' }).click();
  await page.getByLabel('Vrsta').selectOption('sftp');
  await page.getByRole('textbox', { name: 'Naziv' }).fill(name);
  await page.getByRole('textbox', { name: 'Poslužitelj', exact: true }).fill('dockerhost');
  await page.getByRole('textbox', { name: 'Mapa' }).fill(path);
  await page.getByRole('textbox', { name: 'Korisničko ime' }).fill('dock');
  await page.getByLabel('Lozinka', { exact: true }).fill('dockdock');
  await page.getByRole('button', { name: 'Spremi' }).click();
  const link = page.getByRole('link', { name });
  await expect(link).toBeVisible();
  return (await link.getAttribute('href'))!;
}

async function upload(page: Page, name: string, text: string) {
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (await chooser).setFiles([{ name, mimeType: 'text/plain', buffer: Buffer.from(text) }]);
  await expect(page.getByRole('row').filter({ hasText: name })).toBeVisible();
}

const locationOf = (href: string) => decodeURIComponent(href).match(/location:([0-9a-f-]{36})/)![1];

// The backend's tests sign in to the same account and leave their key there, and a file by a name
// already taken is refused.
async function cleared(page: Page, location: string, name: string) {
  await page.evaluate(
    async ({ location, name }) => {
      const at = `/api/locations/${location}`;
      const listed = (await (await fetch(`${at}/files?path=`)).json()) as {
        entries: { name: string }[];
      };
      if (!listed.entries.some((entry) => entry.name === name)) return;
      const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
      const removed = await fetch(`${at}/remove`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
        body: JSON.stringify({ paths: [name] }),
      });
      if (!removed.ok) throw new Error(`POST ${at}/remove: ${removed.status}`);
    },
    { location, name },
  );
}

async function removeLocation(page: Page, name: string) {
  await page.goto('/settings/locations');
  const kept = page.getByRole('listitem').filter({ hasText: name });
  await kept.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Ukloni lokaciju' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Ukloni lokaciju' }).click();
  await expect(kept).toBeHidden();
}

test('a stack on a Docker host is brought up from Files, read and taken down', async ({ page }) => {
  test.slow();
  const stamp = Date.now();
  const name = `Docker ${stamp}`;
  const keys = `Ključevi ${stamp}`;
  const folder = `s${stamp}`;

  const stacks = await addLocation(page, name, 'stacks');
  const locationId = locationOf(stacks);

  await page.goto('/network');
  const hosts = page.getByRole('region', { name: 'Docker domaćini' });
  await hosts.getByRole('button', { name: 'Novi Docker domaćin' }).click();
  const added = page.getByRole('dialog', { name: 'Novi Docker domaćin' });
  await added.getByLabel('Lokacija').selectOption({ label: name });
  await added.getByRole('button', { name: 'Dodaj' }).click();
  const row = hosts.getByRole('listitem').filter({ hasText: name });
  const authorized = (await row.locator('code').textContent())!;
  expect(authorized).toMatch(/^restrict,command="c=\$SSH_ORIGINAL_COMMAND; .*" ssh-ed25519 /);

  const keyFolder = await addLocation(page, keys, '.ssh');
  await cleared(page, locationOf(keyFolder), 'authorized_keys');
  await page.goto(keyFolder);
  await upload(page, 'authorized_keys', `${authorized}\n`);

  await page.goto(stacks);
  await expect(page.getByRole('link', { name: 'Domaćin' })).toBeVisible();
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Nova mapa' }).click();
  await page.getByLabel('Naziv').fill(folder);
  await page.getByRole('button', { name: 'Izradi' }).click();
  await page.getByRole('row').filter({ hasText: folder }).click();
  await upload(page, 'compose.yaml', STACK);
  const folderUrl = page.url();

  const stack = page.getByRole('region', { name: 'Stog' });
  await expect(stack).toContainText('compose.yaml');
  await expect(stack).toContainText('Stog nije pokrenut.');
  await stack.getByRole('button', { name: 'Podigni' }).click();
  const output = page.getByRole('dialog', { name: 'Podigni' });
  await expect(output.getByRole('status')).toHaveText('Gotovo.', { timeout: 60_000 });
  await page.keyboard.press('Escape');

  const app = stack.getByRole('listitem').filter({ hasText: 'app' });
  await expect(app).toContainText('radi');
  await app.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Zapisi' }).click();
  const logs = page.getByRole('dialog', { name: /^Zapisi: / });
  await expect(logs).toContainText('zdravo');
  await page.keyboard.press('Escape');

  await page.goto(`/docker/${locationId}`);
  await expect(page.getByText(/Docker \d+\.\d+/)).toBeVisible();
  await expect(page.getByRole('listitem').filter({ hasText: `${folder}-app-1` })).toContainText(
    'radi',
  );
  await page.getByRole('tab', { name: 'Slike' }).click();
  await expect(page.getByRole('listitem').filter({ hasText: 'ponistra/test:1' })).toBeVisible();

  await page.goto(folderUrl);
  await stack.getByRole('button', { name: 'Radnje' }).first().click();
  await page.getByRole('menuitem', { name: 'Spusti' }).click();
  const down = page.getByRole('dialog', { name: 'Spusti' });
  await expect(down.getByRole('status')).toHaveText('Gotovo.', { timeout: 60_000 });
  await page.keyboard.press('Escape');
  await expect(stack).toContainText('Stog nije pokrenut.');

  await page.goto('/network');
  await row.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Ukloni domaćina' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Ukloni domaćina' }).click();
  await expect(row).toBeHidden();
  await removeLocation(page, keys);
  await removeLocation(page, name);
});
