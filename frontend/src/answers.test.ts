import { QueryClient, QueryObserver } from '@tanstack/react-query';
import { expect, it } from 'vitest';
import { keepAnswers } from './answers';

it('an answer set while a fetch is under way outlasts the fetch', async () => {
  const client = new QueryClient();
  keepAnswers(client);
  let answer: (value: string) => void = () => {};
  const observer = new QueryObserver(client, {
    queryKey: ['vault'],
    queryFn: () => new Promise<string>((resolve) => (answer = resolve)),
  });
  const seen: (string | undefined)[] = [];
  observer.subscribe((result) => seen.push(result.data));
  await Promise.resolve();

  client.setQueryData(['vault'], 'changed');
  answer('before');
  await new Promise((resolve) => setTimeout(resolve));

  expect(client.getQueryData(['vault'])).toBe('changed');
  expect(client.getQueryState(['vault'])?.fetchStatus).toBe('idle');
  expect(seen).not.toContain('before');
});
