import { X } from 'lucide-react';
import { useEffect, useState, useSyncExternalStore } from 'react';
import { useLocation, useSearchParams } from 'react-router';
import { useI18n } from '../i18n';
import { iconButton } from '../styles';
import { Headings, outlineStore } from '../tabs';
import { useTitle } from '../title';
import PdfView from './PdfView';

const ignored = () => {};

/** PDF files opened from the device while nobody is signed in, shown alone across the window
 * and read in the browser, never sent to the server. */
export function DevicePdfs({ files, onClose }: { files: File[]; onClose: () => void }) {
  const { t } = useI18n();
  const [chosen, setChosen] = useState(0);
  const [outline] = useState(outlineStore);
  const bookmarked = Boolean(useSyncExternalStore(outline.subscribe, outline.get)?.headings.length);
  const [params, setParams] = useSearchParams();
  const { key } = useLocation();
  const [url, setUrl] = useState<string | null>(null);
  const [bar, setBar] = useState<HTMLDivElement | null>(null);
  const file = files[Math.min(chosen, files.length - 1)];
  useTitle(file.name);

  useEffect(() => {
    const made = URL.createObjectURL(file);
    setUrl(made);
    return () => URL.revokeObjectURL(made);
  }, [file]);

  return (
    <div className="flex h-dvh flex-col bg-panel text-ink md:flex-row">
      <div className="flex shrink-0 flex-col md:w-80 md:max-w-[35%]">
        <header className="flex items-center gap-1 px-2 pt-2 pb-1">
          {files.length > 1 ? (
            <nav
              className="flex min-w-0 flex-1 gap-1 overflow-x-auto"
              aria-label={t('device.files')}
            >
              {files.map((each, index) => (
                <button
                  key={`${index}:${each.name}`}
                  type="button"
                  aria-pressed={each === file}
                  onClick={() => {
                    setChosen(index);
                    setParams({});
                  }}
                  className="max-w-48 shrink-0 truncate rounded-full px-3 py-1 text-sm text-muted aria-pressed:bg-selected aria-pressed:text-ink"
                >
                  {each.name}
                </button>
              ))}
            </nav>
          ) : (
            <h1 className="min-w-0 flex-1 truncate px-2 text-sm font-medium">{file.name}</h1>
          )}
          <button
            type="button"
            aria-label={t('device.close')}
            title={t('device.close')}
            onClick={() => {
              setParams({});
              onClose();
            }}
            className={iconButton}
          >
            <X size={16} aria-hidden />
          </button>
        </header>
        <div ref={setBar} className="px-1" />
        {bookmarked && (
          <div className="hidden min-h-0 flex-1 overflow-y-auto px-2 pb-2 md:block">
            <Headings
              store={outline}
              indent={0}
              href={(heading) => `?${new URLSearchParams({ heading })}`}
            />
          </div>
        )}
      </div>
      <div className="min-h-0 min-w-0 flex-1 bg-surface px-4 pb-4">
        {url && (
          <PdfView
            key={url}
            file={url}
            page={null}
            heading={params.get('heading')}
            find={null}
            visit={key}
            outline={outline}
            onNoted={ignored}
            onSealed={ignored}
            status={null}
            barIn={bar}
          />
        )}
      </div>
    </div>
  );
}
