import { useMutation } from '@tanstack/react-query';
import { useCallback } from 'react';
import { useNavigate } from 'react-router';
import { postJson } from './api';
import { useSession } from './auth';
import { openBeside } from './meetingWindow';

interface Opening {
  query: string;
  name: string;
}

/** Opens the owner's code workspace (D34) in a named tab, so that a project comes back to its own.
    The one here waits on the backend letting this browser in after a recent confirmation (D33);
    one elsewhere keeps its own door. */
export function useOpenWorkspace() {
  const workspace = useSession().data?.user?.workspace;
  const here = useMutation({
    mutationFn: (_opening: Opening) => postJson('/api/workspace/opened'),
    onSuccess: (_answer, { query, name }) => {
      const address = `/code/${query}`;
      if (!window.open(address, name)) window.location.assign(address);
    },
  });
  return {
    isPending: here.isPending,
    open: (opening: Opening) => {
      if (!workspace) return;
      if (workspace.here) here.mutate(opening);
      else window.open(new URL(opening.query, workspace.url), opening.name);
    },
  };
}

/** The Projects page in a window of its own beside the app, placed as a meeting's. */
export const BESIDE = '/workspace/beside';
const NAMED = 'ponistra-projects';

/** Opens the Projects page beside the app, or brings its window forward; false where the browser
    keeps it from opening. */
export function setAside(): boolean {
  return openBeside(NAMED, BESIDE);
}

/** Going to Projects: on a computer its own window beside the app, as a meeting's, so that the rest
    of the app stays free; on a phone, or where the browser keeps the window from opening, here,
    saying so. */
export function useGoToProjects(): () => void {
  const navigate = useNavigate();
  return useCallback(() => {
    if (!matchMedia('(pointer: fine)').matches) void navigate('/workspace');
    else if (!setAside()) void navigate('/workspace', { state: { blocked: true } });
  }, [navigate]);
}
