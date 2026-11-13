import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';
import { Suspense } from 'react';
import { keepAnswers } from './answers';
import { ApiError } from './api';
import App from './App';
import { SESSION_KEY } from './auth';
import { Confirmation } from './confirmation';
import { followQueries } from './crashes';
import { I18nProvider } from './i18n';
import { Preferences } from './preferences';

function refused(error: Error): boolean {
  return error instanceof ApiError && error.status < 500;
}

/** The client the app's queries share. */
export function newQueryClient(): QueryClient {
  const checkSession = (error: Error) => {
    if (error instanceof ApiError && error.status === 401)
      queryClient.invalidateQueries({ queryKey: SESSION_KEY });
  };
  const queryClient: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: checkSession }),
    mutationCache: new MutationCache({ onError: checkSession }),
    defaultOptions: {
      queries: { retry: (failures, error) => !refused(error) && failures < 3 },
    },
  });
  keepAnswers(queryClient);
  followQueries(queryClient);
  return queryClient;
}

/** The app lays out its pages itself, under one route. */
export const ROUTES = [
  {
    path: '*',
    element: (
      <I18nProvider>
        <Suspense fallback={<div className="min-h-dvh bg-surface" />}>
          <App />
        </Suspense>
        <Confirmation />
        <Preferences />
      </I18nProvider>
    ),
  },
];
