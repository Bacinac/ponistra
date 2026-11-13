import { useCallback, useEffect, useRef, useState } from 'react';
import type { DocumentLocale, Tab } from '../tree';
import type { MeasuredSlide } from './deck';
import { PX_PER_CM } from './pages';
import { settled } from './settled';
import type { GridSource } from './grids';
import { TabDeck, useShows } from './Stage';

/** Every tab's slides laid out as the Slides view lays them, for the printer to read where each
 * box and block shows. `onReady` once they have stopped changing with their fonts and images in,
 * with each tab's slides measured, by the tab's id. */
export default function LaidSlides({
  own,
  tabs,
  states,
  grids,
  locale,
  onReady,
}: {
  own: Uint8Array;
  tabs: readonly Pick<Tab, 'id'>[];
  states: readonly Uint8Array[];
  grids: GridSource;
  locale: DocumentLocale;
  onReady: (slides: Record<string, MeasuredSlide[]>) => void;
}) {
  const shows = useShows(own, tabs, states, grids, locale);
  const measures = useRef(new Map<string, () => MeasuredSlide[]>());
  const changes = useRef(0);
  const [laid, setLaid] = useState(0);
  const onLaid = useCallback((tab: string, measured: () => MeasuredSlide[]) => {
    changes.current += 1;
    measures.current.set(tab, measured);
    setLaid(measures.current.size);
  }, []);

  useEffect(() => {
    if (laid < tabs.length) return;
    let gone = false;
    settled(changes, () => gone).then(
      (done) =>
        done &&
        onReady(
          Object.fromEntries([...measures.current].map(([tab, measured]) => [tab, measured()])),
        ),
    );
    return () => {
      gone = true;
    };
  }, [laid, tabs.length, onReady]);

  const { width, height } = shows.template.size;
  return (
    <main className="ponistra-laid">
      <style>{shows.sheet}</style>
      {shows.tabs.map(({ id }) => (
        <TabDeck
          key={id}
          shows={shows}
          tab={id}
          index={null}
          width={width * PX_PER_CM}
          height={height * PX_PER_CM}
          onLaid={onLaid}
        />
      ))}
    </main>
  );
}
