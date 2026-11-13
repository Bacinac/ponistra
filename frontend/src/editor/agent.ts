import { createContext, useContext, type RefObject } from 'react';
import { getJson } from '../api';
import type { Run } from './runs';

/** A turn of the conversation with the agent beside a document: the user's request and the run
 * that carried it out. */
export interface Turn extends Run {
  request: string;
}

export interface Conversation {
  thread: string | null;
  turns: Turn[];
}

/** Sends the request as a turn of the conversation, over what the editor has selected at that
 * moment, telling `started` once its run is under way. */
export type Asker = (request: string, thread: string, started: () => void) => void;

/** The agent beside the document: the page opens its panel, and the editor of the tab shown
 * sends the panel's requests, once it can. */
export interface Agent {
  open: () => void;
  asker: RefObject<Asker | null>;
}

export const AgentContext = createContext<Agent | null>(null);

export function useAgent(): Agent | null {
  return useContext(AgentContext);
}

/** The user's conversation on the tab's document that `thread` names, or their latest. */
export function conversationOf(tab: string, thread: string | null): Promise<Conversation> {
  const query = thread ? `?${new URLSearchParams({ thread })}` : '';
  return getJson<Conversation>(`/api/tabs/${tab}/runs${query}`);
}
