/* Image loading is local to its reserved frame; it never reloads the document. */
(() => {
  const ui = window.BakaUI = window.BakaUI || {};
  const records = new WeakMap(), mounted = new Set();
  const lifecycle = new AbortController();
  const bind = frame => {
    if (!frame.isConnected || records.has(frame)) return;
    const image = frame.querySelector('[data-media-image]');
    const error = frame.querySelector('[data-media-error]');
    const retry = frame.querySelector('[data-media-retry]');
    if (!image || !error || !retry) return;
    const own = new AbortController(), record = { own, version: 0 };
    records.set(frame, record); mounted.add(frame); frame.dataset.mediaManaged = '';
    const busy = () => {
      record.version++; frame.classList.remove('is-ready', 'is-error');
      frame.classList.add('is-loading'); error.hidden = true;
      frame.setAttribute('aria-busy', 'true');
    };
    const failed = () => {
      record.version++; frame.classList.remove('is-loading', 'is-ready');
      frame.classList.add('is-error'); error.hidden = false;
      frame.setAttribute('aria-busy', 'false');
    };
    const loaded = async () => {
      const version = record.version;
      try { if (image.decode) await image.decode(); }
      catch (_) { if (version === record.version && frame.isConnected) failed(); return; }
      if (version !== record.version || !frame.isConnected || !records.has(frame)) return;
      if (!image.naturalWidth) { failed(); return; }
      frame.classList.remove('is-loading', 'is-error'); frame.classList.add('is-ready');
      frame.setAttribute('aria-busy', 'false'); error.hidden = true;
    };
    image.addEventListener('load', loaded, { signal: own.signal });
    image.addEventListener('error', failed, { signal: own.signal });
    retry.addEventListener('click', () => {
      busy(); const source = image.getAttribute('src');
      image.removeAttribute('src'); image.setAttribute('src', source);
      // Focus survives the disappearing error panel without triggering navigation.
      const target = frame.querySelector('a');
      if (target) target.focus({ preventScroll: true });
      else { frame.tabIndex = -1; frame.focus({ preventScroll: true }); }
    }, { signal: own.signal });
    busy(); if (image.complete) image.naturalWidth ? loaded() : failed();
  };
  const release = frame => {
    const r = records.get(frame); if (!r) return;
    r.version++; r.own.abort(); records.delete(frame); mounted.delete(frame);
    delete frame.dataset.mediaManaged; frame.classList.remove('is-loading', 'is-ready', 'is-error');
    frame.removeAttribute('aria-busy'); frame.querySelector('[data-media-error]').hidden = true;
  };
  const prepare = (scope = document) => {
    if (scope instanceof Element && scope.matches('[data-media-frame]')) bind(scope);
    scope.querySelectorAll('[data-media-frame]').forEach(bind);
  };
  const observer = new MutationObserver(entries => {
    [...mounted].forEach(frame => { if (!frame.isConnected) release(frame); });
    entries.forEach(entry => entry.addedNodes.forEach(n => { if (n instanceof Element) prepare(n); }));
  });
  prepare(); observer.observe(document.body, { childList: true, subtree: true });
  window.addEventListener('pagehide', () => { observer.disconnect(); [...mounted].forEach(release); }, { signal: lifecycle.signal });
  window.addEventListener('pageshow', event => {
    if (event.persisted) { prepare(); observer.observe(document.body, { childList: true, subtree: true }); }
  }, { signal: lifecycle.signal });
  ui.media = { prepare, destroy() { lifecycle.abort(); observer.disconnect(); [...mounted].forEach(release); } };
})();
