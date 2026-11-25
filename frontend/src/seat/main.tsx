import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { I18nProvider } from '../i18n';
import { Seat } from './Seat';
import './seat.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider unchosen="en">
        <Seat />
      </I18nProvider>
    </QueryClientProvider>
  </StrictMode>,
);
