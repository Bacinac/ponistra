import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router';
import { I18nProvider } from '../i18n';
import { installTheme } from '../theme';
import { MachinePage } from './MachinePage';
import { MACHINE_ROUTES } from './routes';
import './machine.css';

installTheme();

const router = createBrowserRouter([
  { path: '/', element: <MachinePage />, children: MACHINE_ROUTES },
]);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nProvider unchosen="en">
      <RouterProvider router={router} />
    </I18nProvider>
  </StrictMode>,
);
