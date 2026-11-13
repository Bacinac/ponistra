(() => {
  const frame = document.querySelector('iframe');
  const { data: address, reads } = frame.dataset;
  const token = () => document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
  const tell = (message) => frame.contentWindow.postMessage(message, '*');

  async function answer({ method, collection, key, body }) {
    if (method === 'CAN') return { value: reads === undefined };
    if (method !== 'GET' && (reads !== undefined || !['PUT', 'PATCH', 'DELETE'].includes(method)))
      return { error: 'read_only' };
    const asked = new URLSearchParams();
    if (collection != null) asked.set('collection', collection);
    if (key != null) asked.set('key', key);
    const response = await fetch(`${address}?${asked}`, {
      method,
      headers:
        method === 'GET' ? {} : { 'Content-Type': 'application/json', 'X-CSRFToken': token() },
      body: method === 'GET' ? undefined : JSON.stringify(body ?? {}),
    });
    const said = await response.json();
    return response.ok ? { value: said } : { error: said.error };
  }

  addEventListener('message', ({ source, data }) => {
    if (source === parent && parent !== window && data?.ponistra === 'changed') tell(data);
    if (source !== frame.contentWindow || typeof data?.ponistra !== 'number') return;
    answer(data).then(
      (answered) => tell({ ponistra: data.ponistra, ...answered }),
      () => tell({ ponistra: data.ponistra, error: 'unreachable' }),
    );
  });
})();
