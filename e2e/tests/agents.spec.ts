import { createHash, randomBytes } from 'node:crypto';
import { expect, test } from './fixtures';

const BACK = 'http://localhost:9/back';
const MCP = {
  Accept: 'application/json, text/event-stream',
  'Content-Type': 'application/json',
  'MCP-Protocol-Version': '2025-06-18',
};

test('a sign-in the installed app is handed goes to the server and asks for consent', async ({
  page,
  baseURL,
}) => {
  const here = (url: string) => new URL(new URL(url).pathname, baseURL).href;
  const metadata = await page.request.get('/.well-known/oauth-authorization-server/api/agents');
  const { authorization_endpoint, registration_endpoint } = await metadata.json();
  const registered = await page.request.post(here(registration_endpoint), {
    data: {
      client_name: 'Claude (e2e)',
      redirect_uris: [BACK],
      token_endpoint_auth_method: 'client_secret_post',
      grant_types: ['authorization_code', 'refresh_token'],
      response_types: ['code'],
    },
  });
  const params = new URLSearchParams({
    client_id: (await registered.json()).client_id,
    redirect_uri: BACK,
    response_type: 'code',
    code_challenge: randomBytes(32).toString('base64url'),
    code_challenge_method: 'S256',
    state: 'e2e',
  });

  await page.goto('/');
  await expect
    .poll(() =>
      page.evaluate(async () =>
        (await navigator.locks.query()).held?.some((lock) => lock.name === 'ponistra-main'),
      ),
    )
    .toBe(true);
  await page.evaluate(
    (target) => {
      const channel = new BroadcastChannel('ponistra-launch');
      channel.postMessage({ target, files: [] });
      channel.close();
    },
    `${here(authorization_endpoint)}?${params}`,
  );

  await expect(
    page
      .getByRole('region', { name: 'Pristup agenta' })
      .getByText('Claude (e2e) traži pristup vašoj Ponistri.'),
  ).toBeVisible();
});

test('an outside agent signs in at the consent page, acts as the user, and is revoked from the account menu', async ({
  page,
  baseURL,
}) => {
  // The doors are named by the installation's public address, which here may not be the one
  // the test reaches it at; the paths are what counts.
  const here = (url: string) => new URL(new URL(url).pathname, baseURL).href;
  const metadata = await page.request.get('/.well-known/oauth-authorization-server/api/agents');
  expect(metadata.ok()).toBe(true);
  const { authorization_endpoint, token_endpoint, registration_endpoint } = await metadata.json();
  expect(new URL(authorization_endpoint).pathname).toBe('/api/agents/authorize');
  const protectedResource = await page.request.get('/.well-known/oauth-protected-resource/api/mcp');
  const { resource } = await protectedResource.json();
  expect(new URL(resource).pathname).toBe('/api/mcp');

  const registered = await page.request.post(here(registration_endpoint), {
    data: {
      client_name: 'Claude (e2e)',
      redirect_uris: [BACK],
      token_endpoint_auth_method: 'client_secret_post',
      grant_types: ['authorization_code', 'refresh_token'],
      response_types: ['code'],
    },
  });
  expect(registered.status()).toBe(201);
  const { client_id, client_secret } = await registered.json();

  const verifier = randomBytes(48).toString('base64url');
  const challenge = createHash('sha256').update(verifier).digest('base64url');
  let returned = '';
  await page.route(`${BACK}**`, (route) => {
    returned = route.request().url();
    return route.fulfill({ status: 200, contentType: 'text/plain', body: 'back' });
  });
  const params = new URLSearchParams({
    client_id,
    redirect_uri: BACK,
    response_type: 'code',
    code_challenge: challenge,
    code_challenge_method: 'S256',
    state: 'e2e',
  });
  await page.goto(`${here(authorization_endpoint)}?${params}`);
  const consent = page.getByRole('region', { name: 'Pristup agenta' });
  await expect(consent.getByText('Claude (e2e) traži pristup vašoj Ponistri.')).toBeVisible();
  await expect(consent.getByText('localhost:9')).toBeVisible();
  await consent.getByRole('button', { name: 'Dopusti' }).click();
  await expect.poll(() => returned).toContain('code=');
  const back = new URL(returned);
  expect(back.searchParams.get('state')).toBe('e2e');
  const code = back.searchParams.get('code')!;

  const tokens = await page.request.post(here(token_endpoint), {
    form: {
      grant_type: 'authorization_code',
      code,
      code_verifier: verifier,
      redirect_uri: BACK,
      client_id,
      client_secret,
      resource,
    },
  });
  expect(tokens.ok()).toBe(true);
  const { access_token } = await tokens.json();
  const call = (method: string, params: object = {}) =>
    page.request.post('/api/mcp', {
      headers: { ...MCP, Authorization: `Bearer ${access_token}` },
      data: { jsonrpc: '2.0', id: 1, method, params },
    });
  const listed = await call('tools/list');
  expect(listed.ok()).toBe(true);
  const names = (await listed.json()).result.tools.map((each: { name: string }) => each.name);
  expect(names).toEqual(expect.arrayContaining(['me', 'search', 'edit_tab', 'draft_reply']));
  const me = await call('tools/call', { name: 'me', arguments: {} });
  const { user } = await (await page.request.get('/api/auth/session')).json();
  expect((await me.json()).result.structuredContent).toEqual({
    user: { id: user.id, name: user.name, email: user.email },
    client: 'Claude (e2e)',
  });

  await page.goto('/settings/agents');
  const settings = page.getByRole('main');
  await expect(settings.getByText(resource)).toBeVisible();
  const row = settings.getByRole('row', { name: /Claude \(e2e\)/ });
  await row.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Opozovi pristup' }).click();
  await page
    .getByRole('alertdialog', { name: 'Opozvati pristup agentu?' })
    .getByRole('button', { name: 'Opozovi pristup' })
    .click();
  await expect(row).toBeHidden();
  await expect(settings.getByText('Nijedan agent još nije povezan.')).toBeVisible();
  expect((await call('tools/list')).status()).toBe(401);
});
