(() => {
  if (parent === window) {
    window.ponistra = Object.freeze({ db: null });
    return;
  }
  const waiting = new Map();
  const watching = new Set();
  let asked = 0;
  let again = null;

  function ask(method, collection, key, body) {
    return new Promise((resolve, reject) => {
      asked += 1;
      waiting.set(asked, { resolve, reject });
      parent.postMessage({ ponistra: asked, method, collection, key, body }, '*');
    });
  }

  const shown = ({ key, data, version }) => ({ id: key, exists: true, version, data: () => data });
  const absent = (key) => ({ id: key, exists: false, version: 0, data: () => undefined });

  function watch(read, next, failed) {
    const watcher = {
      last: null,
      refresh() {
        read().then(({ text, value }) => {
          if (text === watcher.last) return;
          watcher.last = text;
          next(value);
        }, failed ?? (() => {}));
      },
    };
    watching.add(watcher);
    watcher.refresh();
    return () => watching.delete(watcher);
  }

  function doc(collection, key) {
    const write = (method, data, options) =>
      ask(method, collection, key, { data, if_version: options?.ifVersion }).then(shown);
    const read = () =>
      ask('GET', collection, key).then(shown, (error) => {
        if (error.code === 'not_found') return absent(key);
        throw error;
      });
    return {
      id: key,
      get: read,
      set: (data, options) => write('PUT', data, options),
      update: (data, options) => write('PATCH', data, options),
      delete: () => ask('DELETE', collection, key, {}).then(() => undefined),
      onSnapshot: (next, failed) =>
        watch(
          () =>
            read().then((value) => ({
              text: JSON.stringify([value.version, value.data()]),
              value,
            })),
          next,
          failed,
        ),
    };
  }

  function collection(name) {
    const read = () =>
      ask('GET', name).then(({ entries }) => ({
        text: JSON.stringify(entries),
        value: { docs: entries.map(shown), size: entries.length, empty: !entries.length },
      }));
    return {
      id: name,
      doc: (key) => doc(name, key),
      get: () => read().then(({ value }) => value),
      onSnapshot: (next, failed) => watch(read, next, failed),
    };
  }

  addEventListener('message', ({ source, data }) => {
    if (source !== parent || !data) return;
    if (data.ponistra === 'changed') {
      clearTimeout(again);
      again = setTimeout(() => watching.forEach((watcher) => watcher.refresh()), 250);
      return;
    }
    const pending = waiting.get(data.ponistra);
    if (!pending) return;
    waiting.delete(data.ponistra);
    if (data.error === undefined) pending.resolve(data.value);
    else pending.reject(Object.assign(new Error(data.error), { code: data.error }));
  });

  window.ponistra = Object.freeze({
    db: Object.freeze({
      canWrite: () => ask('CAN'),
      collection,
      doc: (path) => {
        const [name, key, ...rest] = path.split('/');
        if (!key || rest.length) throw new Error(`Not a document's path: ${path}`);
        return doc(name, key);
      },
    }),
  });
})();
