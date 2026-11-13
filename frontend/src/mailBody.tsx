import { useEffect, useRef, useState } from 'react';

const FRAME_POLICY =
  "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; font-src data:";
/* Inside the message's own frame, which none of the interface's styles reach. */
const FRAME_STYLE =
  'html{font:14px/1.5 system-ui,sans-serif;overflow-wrap:break-word}body{margin:0;padding:16px}img{max-width:100%}img:not([src]){visibility:hidden}';

/** The message's HTML in a frame of its own: nothing in it runs, it reaches no other server (its
    images from elsewhere come through ours once the reader lets them in), and it keeps the light
    paper mail is written for. */
export function HtmlBody({ title, html }: { title: string; html: string }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(0);
  const page =
    `<!doctype html><html><head><meta charset="utf-8">` +
    `<meta http-equiv="Content-Security-Policy" content="${FRAME_POLICY}">` +
    `<meta name="color-scheme" content="light"><base target="_blank">` +
    `<style>${FRAME_STYLE}</style></head><body>${html}</body></html>`;
  useEffect(() => {
    const element = frame.current;
    if (!element) return;
    let watcher: ResizeObserver | undefined;
    const fit = () => {
      const inside = element.contentDocument;
      if (!inside?.body) return;
      const measure = () => setHeight(inside.documentElement.scrollHeight);
      measure();
      watcher?.disconnect();
      watcher = new ResizeObserver(measure);
      watcher.observe(inside.body);
    };
    element.addEventListener('load', fit);
    return () => {
      element.removeEventListener('load', fit);
      watcher?.disconnect();
    };
  }, []);
  return (
    <div className="overflow-hidden rounded-lg bg-raised scheme-light">
      <iframe
        ref={frame}
        title={title}
        srcDoc={page}
        sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
        className="block w-full"
        style={{ height }}
      />
    </div>
  );
}
