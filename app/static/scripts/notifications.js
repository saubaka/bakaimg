(() => {
  const ui = window.BakaUI, toastRegion = document.querySelector('[data-toast-region]');
  const records = new Map(), lifecycle = new AbortController(); let destroyed = false;
  const remove = toast => {
    const state = records.get(toast); if (!state) return;
    clearTimeout(state.timer); state.listeners.abort(); ui.surfaces.clear(toast); records.delete(toast); toast.remove();
    toastRegion.hidden = !toastRegion.children.length;
  };
  const dismiss = async toast => {
    const state = records.get(toast); if (!state || state.leaving) return;
    state.leaving = true; clearTimeout(state.timer); toast.classList.add('is-leaving');
    if (await ui.surfaces.move(toast, false)) remove(toast);
  };
  const manage = toast => {
    if (destroyed || records.has(toast)) return;
    const persistent = toast.matches('.ba-toast--error');
    const state = { timer: 0, remaining: 4600, persistent,
      deadline: 0, leaving: false, hovered: false, focused: false, listeners: new AbortController() };
    records.set(toast, state); toastRegion.hidden = false; toast.classList.add('is-toast-managed');
    const dot = document.createElement('i'); dot.setAttribute('aria-hidden', 'true');
    const text = document.createElement('span'); text.textContent = toast.textContent; toast.replaceChildren(dot, text);
    const close = document.createElement('button'); close.type = 'button';
    close.textContent = '×'; close.setAttribute('aria-label', '关闭提示'); toast.append(close);
    close.addEventListener('click', () => dismiss(toast), { signal: state.listeners.signal });
    const sync = () => {
      if (state.leaving) return;
      if (state.timer) { clearTimeout(state.timer); state.timer = 0; state.remaining = Math.max(0, state.deadline - performance.now()); }
      if (state.persistent) return;
      if (!state.hovered && !state.focused) { state.deadline = performance.now() + state.remaining; state.timer = setTimeout(() => dismiss(toast), state.remaining); }
    };
    toast.addEventListener('pointerenter', () => { state.hovered = true; sync(); }, { signal: state.listeners.signal });
    toast.addEventListener('pointerleave', () => { state.hovered = false; sync(); }, { signal: state.listeners.signal });
    toast.addEventListener('focusin', () => { state.focused = true; sync(); }, { signal: state.listeners.signal });
    toast.addEventListener('focusout', event => { if (!toast.contains(event.relatedTarget)) { state.focused = false; sync(); } }, { signal: state.listeners.signal });
    ui.surfaces.move(toast, true).then(finished => { if (finished && records.has(toast) && !state.leaving) sync(); });
  };
  const notify = (message, category = 'info') => {
    if (destroyed || !toastRegion || !message) return;
    category = ['success', 'info', 'warning', 'error'].includes(category) ? category : 'info';
    const existing = [...records].find(([node, state]) => !state.leaving && node.querySelector('span')?.textContent === message && node.dataset.toastCategory === category);
    if (existing) return existing[0];
    const toast = document.createElement('div');
    toast.className = 'ba-toast' + (category === 'success' ? ' ba-toast--ok' : ['warning', 'error'].includes(category) ? ' ba-toast--error' : '');
    toast.dataset.toast = ''; toast.dataset.toastCategory = category;
    toast.setAttribute('role', ['warning', 'error'].includes(category) ? 'alert' : 'status'); toast.textContent = message;
    toastRegion.append(toast); manage(toast); return toast;
  };
  const viewport = () => {
    const view = window.visualViewport;
    const keyboard = view ? Math.max(0, innerHeight - view.height - view.offsetTop) : 0;
    toastRegion?.style.setProperty('--notice-keyboard', keyboard + 'px');
  };
  const clear = () => [...records.keys()].forEach(remove);
  toastRegion?.querySelectorAll('[data-toast]').forEach(manage);
  if (toastRegion && !toastRegion.children.length) toastRegion.hidden = true;
  window.visualViewport?.addEventListener('resize', viewport, { signal: lifecycle.signal });
  window.visualViewport?.addEventListener('scroll', viewport, { signal: lifecycle.signal });
  window.addEventListener('pagehide', clear, { signal: lifecycle.signal });
  ui.notifications = { notify, dismiss, destroy() { destroyed = true; clear(); lifecycle.abort(); } };
})();
