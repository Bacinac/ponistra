import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router';
import { installFonts } from './fonts';
import { installPush } from './push';
import { followPage, reloadOnce } from './release';
import { newQueryClient, ROUTES } from './root';
import { installTheme } from './theme';
import './index.css';

const queryClient = newQueryClient();

// An update takes away the chunks of the build an open page came from, so a page it has not shown
// yet comes from the new build; one the new build fails to bring as well shows its error.
window.addEventListener('vite:preloadError', reloadOnce);

installFonts();
installTheme();
installPush();
followPage();

const router = createBrowserRouter(ROUTES);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
