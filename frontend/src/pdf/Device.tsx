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
  const file = files[Math.min(chosen, files.length - 1)];
  useTitle(file.name);

  useEffect(() => {
    const made = URL.createObjectURL(file);
    setUrl(made);
    return () => URL.revokeObjectURL(made);
  }, [file]);

  return (
    <div className="flex h-dvh bg-panel text-ink">
      {bookmarked && (
        <div className="hidden w-72 max-w-[30%] shrink-0 overflow-y-auto px-2 pt-14 pb-2 md:block">
          <Headings
            store={outline}
            indent={0}
            href={(heading) => `?${new URLSearchParams({ heading })}`}
          />
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col bg-surface p-4 pt-3">
        <header className="flex items-center gap-2 pb-3">
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
                  className="max-w-60 shrink-0 truncate rounded-full px-3 py-1 text-sm text-muted aria-pressed:bg-selected aria-pressed:text-ink"
                >
                  {each.name}
                </button>
              ))}
            </nav>
          ) : (
            <h1 className="min-w-0 flex-1 truncate px-1 font-medium">{file.name}</h1>
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
            <X size={18} aria-hidden />
          </button>
        </header>
        <div className="min-h-0 flex-1">
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
            />
          )}
        </div>
      </div>
    </div>
  );
}
