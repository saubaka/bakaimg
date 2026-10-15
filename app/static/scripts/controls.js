(() => {
  const ui = window.BakaUI = window.BakaUI || {};
  const records = new WeakMap(), mounted = new Set(), listeners = new AbortController();
  const selector = '[data-discover-menu], [data-upload-visibility]';
  const bind = menu => {
    if (!menu.isConnected) return;
    if (records.has(menu)) return;
    const kind = menu.matches('[data-discover-menu]') ? 'discover-menu' : 'upload-visibility';
    const trigger = menu.querySelector(`[data-${kind}-trigger]`);
    const panel = menu.querySelector(`[data-${kind}-${kind === 'discover-menu' ? 'panel' : 'menu'}]`);
    const value = menu.querySelector(`[data-${kind}-${kind === 'discover-menu' ? 'value' : 'native'}]`);
    const label = menu.querySelector(`[data-${kind}-label]`);
    const options = [...menu.querySelectorAll(`[data-${kind}-option]`)];
    if (!trigger || !panel || !value || !label) return;
    if (value.tagName === 'SELECT' && menu.classList.contains('visibility-control')) {
      value.tabIndex = -1; value.setAttribute('aria-hidden', 'true'); menu.classList.add('is-enhanced');
    }
    const own = new AbortController();
    const record = { menu, panel, trigger, own, open: false, animation: null, version: 0 };
    records.set(menu, record); mounted.add(menu); panel.dataset.controlPanel = '';
    const setOpen = (open, focusOption = false) => {
      if (open === record.open) return;
      record.open = open;
      const version = ++record.version;
      trigger.setAttribute('aria-expanded', String(open));
      menu.classList.toggle('is-open', open);
      panel.inert = !open;
      if (open) panel.hidden = false;
      const finish = () => {
        if (record.version !== version) return;
        panel.hidden = !open;
        record.animation?.pause();
      };
      if (ui.motion.reduced()) {
        record.animation?.cancel(); record.animation = null; finish();
      } else {
        try {
          if (!record.animation) {
            record.animation = panel.animate([{ opacity: 0, transform: 'translateY(-6px)' },
              { opacity: 1, transform: 'translateY(0)' }],
            { duration: 240, easing: 'cubic-bezier(.2,.78,.22,1)', fill: 'both' });
            record.animation.pause(); record.animation.currentTime = 0;
          }
          record.animation.updatePlaybackRate(open ? 1 : -1); record.animation.play();
          record.animation.finished.then(finish).catch(() => {});
        } catch (_) { finish(); }
      }
      if (open && focusOption) (options.find(n => n.getAttribute('aria-checked') === 'true') || options[0])?.focus();
    };
    record.setOpen = setOpen;
    trigger.addEventListener('click', () => setOpen(!record.open, true), { signal: own.signal });
    options.forEach(option => option.addEventListener('click', () => {
      value.value = option.getAttribute(`data-${kind}-option`);
      value.dispatchEvent(new Event('change', { bubbles: true }));
      label.textContent = option.querySelector('span')?.textContent || option.textContent.trim();
      options.forEach(item => item.setAttribute('aria-checked', String(item === option)));
      setOpen(false); trigger.focus();
    }, { signal: own.signal }));
    menu.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); setOpen(false); trigger.focus(); return; }
      if (!['ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
      event.preventDefault(); setOpen(true);
      const current = Math.max(0, options.indexOf(document.activeElement));
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1
        : event.key === 'ArrowDown' ? (current + 1) % options.length : (current - 1 + options.length) % options.length;
      options[next]?.focus();
    }, { signal: own.signal });
  };
  const release = menu => {
    const r = records.get(menu); if (!r) return;
    r.version++; r.animation?.cancel(); r.own.abort();
    r.panel.hidden = true; r.panel.inert = false; delete r.panel.dataset.controlPanel;
    menu.classList.remove('is-open'); r.trigger.setAttribute('aria-expanded','false');
    if (menu.classList.contains('visibility-control')) {
      menu.classList.remove('is-enhanced'); const value = menu.querySelector('select');
      value?.removeAttribute('aria-hidden'); value?.removeAttribute('tabindex');
    }
    records.delete(menu); mounted.delete(menu);
  };
  const prepare = (scope = document) => {
    if (scope instanceof Element && scope.matches(selector)) bind(scope);
    scope.querySelectorAll(selector).forEach(bind);
  };
  document.addEventListener('pointerdown', event => {
    mounted.forEach(menu => { if (!menu.contains(event.target)) records.get(menu).setOpen(false); });
  }, { signal: listeners.signal });
  // 按钮的按下效果由设计系统的 :active 样式负责，这里不再记录按下状态。
  const clearPress = () => {};
  const mutation = new MutationObserver(entries => {
    [...mounted].forEach(menu => { if (!menu.isConnected) release(menu); });
    entries.forEach(entry => entry.addedNodes.forEach(node => { if (node instanceof Element) prepare(node); }));
  });
  mutation.observe(document.body, { childList: true, subtree: true });
  const syncPreferences = () => {
    if (!ui.motion.reduced()) return;
    mounted.forEach(menu => {
      const r = records.get(menu); r.version++;
      r.animation?.cancel(); r.animation = null; r.panel.hidden = !r.open;
    });
  };
  const preferences = new MutationObserver(syncPreferences);
  preferences.observe(document.documentElement, { attributes: true, attributeFilter: ['data-motion','data-performance'] });
  matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', syncPreferences, { signal: listeners.signal });
  window.addEventListener('pagehide', () => {
    clearPress(); mutation.disconnect(); preferences.disconnect();
    [...mounted].forEach(release);
  }, { signal: listeners.signal });
  window.addEventListener('pageshow', event => {
    if (event.persisted) {
      prepare(); mutation.observe(document.body, { childList: true, subtree: true });
      preferences.observe(document.documentElement, { attributes: true, attributeFilter: ['data-motion','data-performance'] });
    }
  }, { signal: listeners.signal });
  ui.controls = { prepare, destroy() { listeners.abort(); mutation.disconnect(); preferences.disconnect(); [...mounted].forEach(release); clearPress(); } };
})();
