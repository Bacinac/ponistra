import { useRef, type MouseEvent, type PointerEvent } from 'react';
import { flushSync } from 'react-dom';

// How long a pointer stays on a row before it is chosen, and how far it may wander meanwhile.
const PRESS = 500;
const PRESS_SLOP = 10;

export function scrollerOf(element: Element): Element | null {
  for (let at = element.parentElement; at; at = at.parentElement)
    if (/auto|scroll/.test(getComputedStyle(at).overflowY)) return at;
  return null;
}

/** Makes a change that brings the bar of a list or takes it away, keeping the row where the
    pointer has it and clear of the bar. */
export function steady(row: Element, change: () => void) {
  const before = row.getBoundingClientRect().top;
  flushSync(change);
  const scroller = scrollerOf(row);
  if (!scroller) return;
  const bar = scroller.querySelector<HTMLElement>('[data-choice-bar]');
  const clear = bar ? scroller.getBoundingClientRect().top + bar.offsetHeight : before;
  scroller.scrollTop += row.getBoundingClientRect().top - Math.max(before, clear);
}

/** Calls a row's `onPress` once a pointer has stayed on it for a while, or a touch screen asks for
    its menu; `pressed` tells the click that ends such a press, which has done its work already. */
export function useLongPress() {
  const timer = useRef<number>(undefined);
  const start = useRef<{ x: number; y: number } | null>(null);
  const fired = useRef(false);
  const stop = () => {
    window.clearTimeout(timer.current);
    start.current = null;
  };
  const press = (onPress: () => void) => {
    const fire = (row: Element) => {
      stop();
      fired.current = true;
      steady(row, onPress);
    };
    return {
      onPointerDown: (event: PointerEvent) => {
        if (event.button !== 0) return;
        // A touch press is the row's own: a context menu around it would open on it too.
        if (event.pointerType !== 'mouse') event.preventDefault();
        fired.current = false;
        start.current = { x: event.clientX, y: event.clientY };
        const row = event.currentTarget;
        timer.current = window.setTimeout(() => fire(row), PRESS);
      },
      onPointerMove: (event: PointerEvent) => {
        const from = start.current;
        if (from && Math.hypot(event.clientX - from.x, event.clientY - from.y) > PRESS_SLOP) stop();
      },
      onPointerUp: stop,
      onPointerCancel: stop,
      onContextMenu: (event: MouseEvent) => {
        if (!start.current && !fired.current) return;
        event.preventDefault();
        if (!fired.current) fire(event.currentTarget);
      },
    };
  };
  const pressed = () => {
    const was = fired.current;
    fired.current = false;
    return was;
  };
  return [press, pressed] as const;
}

/** Opens the context menu around an element on a mouse's long press too, as a touch screen's long
    press opens it. */
export function useMenuPress() {
  const timer = useRef<number>(undefined);
  const start = useRef<{ x: number; y: number } | null>(null);
  const stop = () => {
    window.clearTimeout(timer.current);
    start.current = null;
  };
  return {
    onPointerDown: (event: PointerEvent) => {
      if (event.pointerType !== 'mouse' || event.button !== 0) return;
      const { currentTarget, clientX, clientY } = event;
      start.current = { x: clientX, y: clientY };
      timer.current = window.setTimeout(() => {
        stop();
        currentTarget.dispatchEvent(
          new globalThis.MouseEvent('contextmenu', {
            bubbles: true,
            cancelable: true,
            clientX,
            clientY,
          }),
        );
      }, PRESS);
    },
    onPointerMove: (event: PointerEvent) => {
      const from = start.current;
      if (from && Math.hypot(event.clientX - from.x, event.clientY - from.y) > PRESS_SLOP) stop();
    },
    onPointerUp: stop,
    onPointerCancel: stop,
    onDragStart: stop,
  };
}
