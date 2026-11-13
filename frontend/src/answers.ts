import type { QueryClient } from '@tanstack/react-query';

/** Data set by hand is the server's answer to a change; a fetch begun before the change would
    land after it with the state from before, so it is dropped. */
export function keepAnswers(client: QueryClient) {
  return client.getQueryCache().subscribe((event) => {
    if (
      event.type === 'updated' &&
      event.action.type === 'success' &&
      event.action.manual &&
      event.query.state.fetchStatus === 'fetching'
    )
      void event.query.cancel({ revert: true });
  });
}
