import { openBeside } from './meetingWindow';

export const START = '/start';

/** The links open in a window of their own on a computer, as a browser's start page; false on a
    phone or where the browser keeps the window from opening, which stay on /links. */
export function openLinks(): boolean {
  return matchMedia('(pointer: fine)').matches && openBeside('ponistra-links', START);
}
