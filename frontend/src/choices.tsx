import { MoveHorizontal, RectangleVertical, type LucideIcon } from 'lucide-react';
import { useI18n } from './i18n';
import { iconButton } from './styles';
import { ZOOMS, type Zoom } from './views';

/** One of a few ways to show what is open, as toggles on its bar. */
export function Choices<T extends string>({
  label,
  choices,
  chosen,
  icons,
  labelOf,
  onChoose,
}: {
  label: string;
  choices: readonly T[];
  chosen: T;
  icons: Record<T, LucideIcon>;
  labelOf: (choice: T) => string;
  onChoose: (choice: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex items-center gap-0.5">
      {choices.map((each) => {
        const Icon: LucideIcon = icons[each];
        return (
          <button
            key={each}
            type="button"
            aria-label={labelOf(each)}
            title={labelOf(each)}
            aria-pressed={chosen === each}
            onClick={() => onChoose(each)}
            className={`${iconButton} aria-pressed:bg-selected aria-pressed:text-accent`}
          >
            <Icon size={16} aria-hidden />
          </button>
        );
      })}
    </div>
  );
}

const ZOOM_ICONS: Record<Zoom, LucideIcon> = { page: RectangleVertical, width: MoveHorizontal };

/** How large pages show, the same for a document's pages and slides and a PDF file's. */
export function ZoomChoices({ zoom, onChoose }: { zoom: Zoom; onChoose: (zoom: Zoom) => void }) {
  const { t } = useI18n();
  return (
    <Choices
      label={t('zoom.label')}
      choices={ZOOMS}
      chosen={zoom}
      icons={ZOOM_ICONS}
      labelOf={(each) => t(`zoom.${each}`)}
      onChoose={onChoose}
    />
  );
}
