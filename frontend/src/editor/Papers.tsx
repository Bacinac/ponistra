import { DOMSerializer } from 'prosemirror-model';
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { yXmlFragmentToProseMirrorRootNode } from 'y-prosemirror';
import type * as Y from 'yjs';
import type { GridSource } from './grids';
import {
  opensSection,
  PARTS,
  PX_PER_CM,
  type PagePlace,
  type Part,
  type PartHeights,
  type Section,
  type Stack,
} from './pages';
import { valueOf, type Fields, type Writing } from './parts';
import { schema } from './schema';
import { PaperTable } from './sheet';
import { layTabs } from './stops';

/** Each header's and footer's blocks drawn as paper shows them, by its fragment. */
type Templates = Map<Y.XmlFragment, Node>;

function templatesOf(sections: readonly Section[], grids: GridSource): Templates {
  const serializer = DOMSerializer.fromSchema(schema);
  const templates: Templates = new Map();
  for (const fragment of sections.flatMap(({ parts }) => Object.values(parts))) {
    if (templates.has(fragment)) continue;
    const content = document.createDocumentFragment();
    yXmlFragmentToProseMirrorRootNode(fragment, schema).forEach((block) => {
      content.append(
        block.type === schema.nodes.table
          ? new PaperTable(block, grids.grid(block.attrs.id)).whole()
          : serializer.serializeNode(block),
      );
    });
    templates.set(fragment, content);
  }
  return templates;
}

function useTemplates(sections: readonly Section[], grids: GridSource): Templates {
  const changed = useOwnGrids(grids);
  return useMemo(() => templatesOf(sections, grids), [sections, grids, changed]);
}

/** The grids of the headers and footers, every row of them held; changes each time one does. */
function useOwnGrids(grids: GridSource): number {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const owner = {};
    const hold = () => {
      for (const grid of grids.tables()) {
        if (grid.tab === null) grids.show(owner, grid.table, [[0, grid.rowCount - 1]]);
      }
    };
    hold();
    const off = grids.subscribe(null, (change) => {
      const grid = grids.grid(change.table);
      if (grid && grid.tab !== null) return;
      if (change.outline) hold();
      setVersion((each) => each + 1);
    });
    return () => {
      off();
      grids.forget(owner);
    };
  }, [grids]);
  return version;
}

/** The part a page shows on that side: the own one of its section's first page where the section
 * sets that apart. */
export function partOn(side: Writing['side'], opening: boolean, firstApart: boolean): Part {
  return firstApart && opening ? `${side}First` : side;
}

/** Where a page's header starts, or its footer ends, both as wide as the page's text. */
export function partPlace(
  { top, left, geometry }: PagePlace,
  side: Writing['side'],
): CSSProperties {
  return {
    top: side === 'header' ? top + geometry.header : top + geometry.height - geometry.footer,
    left: left + geometry.left,
    width: geometry.width - geometry.left - geometry.right,
  };
}

function PagePart({
  template,
  page,
  fields,
  decimal,
  className,
  style,
}: {
  template: Node | undefined;
  page: number;
  fields: Fields;
  decimal: string;
  className: string;
  style?: CSSProperties;
}) {
  const box = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = box.current!;
    element.replaceChildren(template ? template.cloneNode(true) : '');
    for (const field of element.querySelectorAll<HTMLElement>('[data-field]')) {
      field.textContent = valueOf(field.dataset.field, page, fields);
    }
    layTabs(element, decimal);
  }, [template, page, fields, decimal]);
  return <div ref={box} className={`ponistra-part ${className}`} style={style} />;
}

/** Each section's headers and footers off the page, as wide as its text, how tall each shows
 * going to `onHeights` by the section's place among the tab's. */
export function PartMeasures({
  sections,
  fields,
  decimal,
  scope,
  grids,
  onHeights,
}: {
  sections: readonly Section[];
  fields: Fields;
  decimal: string;
  scope: string;
  grids: GridSource;
  onHeights: (heights: PartHeights[]) => void;
}) {
  const templates = useTemplates(sections, grids);
  const measured = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = measured.current!;
    const read = () =>
      onHeights(
        [...element.children].map((section) => {
          const heights: PartHeights = {};
          for (const child of section.children as HTMLCollectionOf<HTMLElement>) {
            heights[child.dataset.part as Part] = child.offsetHeight;
          }
          return heights;
        }),
      );
    read();
    const observer = new ResizeObserver(read);
    for (const child of element.querySelectorAll('[data-part]')) observer.observe(child);
    return () => observer.disconnect();
  }, [sections, templates, fields, decimal, onHeights]);
  return (
    <div ref={measured} data-styling={scope} aria-hidden className="ponistra-measured">
      {sections.map(({ setup, parts }, index) => (
        <div key={index} style={{ width: (setup.width - setup.left - setup.right) * PX_PER_CM }}>
          {PARTS.filter((name) => parts[name]).map((name) => (
            <div key={name} data-part={name}>
              <PagePart
                template={templates.get(parts[name]!)}
                page={fields.first}
                fields={fields}
                decimal={decimal}
                className=""
                style={{ position: 'static' }}
              />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

/** White pages on a grey field behind the tab's text, each with its section's header and footer;
 * a section's first page has its own where the section sets one apart. The part being written is
 * left to its editor. */
export function Papers({
  stack,
  sections,
  numbers,
  fields,
  decimal,
  scope,
  writing,
  grids,
}: {
  stack: Stack;
  sections: readonly Section[];
  /** Each page's number. */
  numbers: readonly number[];
  fields: Fields;
  /** The document language's decimal separator, which decimal tab stops line numbers up on. */
  decimal: string;
  scope: string;
  writing: Writing | null;
  /** Where the tables of the headers and footers have their grids. */
  grids: GridSource;
}) {
  const templates = useTemplates(sections, grids);
  const owners = stack.pages.map(({ section }) => section);
  return (
    <div data-styling={scope} aria-hidden className="ponistra-papers">
      {stack.pages.map((place, index) => {
        const { parts, setup } = sections[place.section];
        const opening = opensSection(owners, index);
        const shown = (side: Writing['side']) => writing?.side !== side || writing.page !== index;
        return (
          <div key={index}>
            <div
              className="ponistra-paper"
              style={{
                top: place.top,
                left: place.left,
                width: place.geometry.width,
                height: place.geometry.height,
              }}
            />
            {(['header', 'footer'] as const).filter(shown).map((side) => {
              const part = parts[partOn(side, opening, setup.firstPage)];
              return (
                <PagePart
                  key={side}
                  template={part && templates.get(part)}
                  page={numbers[index]}
                  fields={fields}
                  decimal={decimal}
                  className={`ponistra-${side}`}
                  style={partPlace(place, side)}
                />
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
