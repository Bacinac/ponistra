import {
  CalendarDays,
  Files,
  FolderTree,
  type LucideIcon,
  Mail,
  MessagesSquare,
  Sun,
} from 'lucide-react';

export type Module = 'today' | 'calendar' | 'mail' | 'documents' | 'files' | 'chat';

/** The rail holds every module, down the side of a wide screen and along the foot of a phone. */
export const MODULES: { id: Module; icon: LucideIcon; to: string }[] = [
  { id: 'today', icon: Sun, to: '/' },
  { id: 'calendar', icon: CalendarDays, to: '/calendar' },
  { id: 'mail', icon: Mail, to: '/mail' },
  { id: 'chat', icon: MessagesSquare, to: '/chat' },
  { id: 'documents', icon: Files, to: '/documents' },
  { id: 'files', icon: FolderTree, to: '/files' },
];
