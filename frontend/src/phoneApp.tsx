import { Download, Smartphone } from 'lucide-react';
import { useMemo } from 'react';
import { encode } from 'uqr';
import shelved from 'virtual:android';
import { formatSize } from './explorer';
import { Lobby } from './frame';
import { useI18n } from './i18n';
import { button, primaryButton } from './styles';

const PACKAGE = 'biz.boskovic.ponistra';
export const onAndroid = /Android/.test(navigator.userAgent);

/** Where a phone that scans the pairing code lands, the code in the fragment, which no server
    and no log sees. */
export function connectPage(code: string): string {
  return `${location.origin}/connect#${encodeURIComponent(code)}`;
}

/** Chrome hands the app the pairing code, or, where the app is not installed, loads the page that
    offers it instead. */
function connectLink(code: string): string {
  const query = new URLSearchParams({ origin: location.origin, code });
  const back = encodeURIComponent(connectPage(code));
  return `intent://connect?${query}#Intent;scheme=ponistra;package=${PACKAGE};S.browser_fallback_url=${back};end`;
}

export function Qr({ text, label }: { text: string; label: string }) {
  const modules = useMemo(() => encode(text, { ecc: 'M', border: 2 }).data, [text]);
  const path = modules
    .flatMap((row, y) => row.map((dark, x) => (dark ? `M${x} ${y}h1v1h-1z` : '')))
    .join('');
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${modules.length} ${modules.length}`}
      shapeRendering="crispEdges"
      className="size-56 rounded bg-scan text-scan-ink"
    >
      <path d={path} fill="currentColor" />
    </svg>
  );
}

/** On the phone itself: the app to install, then the link that opens it with the code. */
export function Steps({ code }: { code: string }) {
  const { t, formatNumber } = useI18n();
  if (!shelved) return null;
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p>{t('phoneApp.steps')}</p>
      <div className="flex flex-wrap gap-2">
        <a href="/android/ponistra.apk" download="ponistra.apk" className={button}>
          <Download size={16} aria-hidden />
          {`${t('phoneApp.download')} (${shelved.versionName}, ${formatSize(shelved.bytes, formatNumber)})`}
        </a>
        <a href={connectLink(code)} className={primaryButton}>
          <Smartphone size={16} aria-hidden />
          {t('phoneApp.open')}
        </a>
      </div>
    </div>
  );
}

/** The page a scanned pairing code opens on the phone, before any sign-in: the code is all the
    app needs. */
export function ConnectPage() {
  const { t } = useI18n();
  const code = decodeURIComponent(location.hash.slice(1));
  return (
    <Lobby>
      <section className="flex w-full max-w-md flex-col gap-3">
        <h2 className="text-lg font-semibold">{t('phoneApp.title')}</h2>
        {!onAndroid ? (
          <p className="text-sm">{t('phoneApp.androidOnly')}</p>
        ) : code ? (
          <Steps code={code} />
        ) : (
          <p className="text-sm">{t('phoneApp.noCode')}</p>
        )}
      </section>
    </Lobby>
  );
}
