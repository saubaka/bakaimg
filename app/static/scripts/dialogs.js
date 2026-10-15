(() => {
  const ui = window.BakaUI;
  const dialog = document.querySelector('[data-app-system-dialog]');
  const lifecycle = new AbortController(), options = { signal: lifecycle.signal };
  let pending = null, version = 0, destroyed = false;
  const cancelValue = entry => entry?.mode === 'prompt' ? null : false;
  const viewport = () => {
    if (!dialog?.open) return;
    const view = window.visualViewport;
    dialog.style.setProperty('--dialog-visible-height', (view?.height || innerHeight) + 'px');
    dialog.style.setProperty('--dialog-visible-top', (view?.offsetTop || 0) + 'px');
  };
  const reset = () => {
    ++version; const previous = pending; pending = null;
    ui.surfaces.clear(dialog); if (dialog?.open) dialog.close();
    previous?.resolve(cancelValue(previous));
  };
  const settle = async value => {
    if (!pending || pending.closing) return;
    const entry = pending, current = ++version; entry.closing = true;
    const finished = await ui.surfaces.move(dialog, false);
    if (!finished || version !== current || pending !== entry) return;
    pending = null; dialog.close(); dialog.querySelector('[data-app-dialog-input]').value = '';
    if (entry.trigger?.isConnected) entry.trigger.focus({ preventScroll: true });
    entry.resolve(value);
  };
  const request = ({ mode = 'confirm', title, message = '', value = '', inputLabel = '请输入内容', danger = false }) => {
    if (destroyed || !dialog) return Promise.resolve(mode === 'prompt' ? null : false);
    const previous = pending; previous?.resolve(cancelValue(previous));
    const trigger = previous?.trigger || document.activeElement, current = ++version;
    const input = dialog.querySelector('[data-app-dialog-input]');
    dialog.dataset.dialogMode = mode; dialog.dataset.dialogTone = danger ? 'danger' : 'default';
    dialog.querySelector('[data-app-dialog-title]').textContent = title || (mode === 'prompt' ? '输入内容' : mode === 'alert' ? '提示' : '确认操作');
    dialog.querySelector('[data-app-dialog-message]').textContent = message;
    dialog.querySelector('[data-app-dialog-input-label]').textContent = inputLabel;
    dialog.querySelector('[data-app-dialog-field]').hidden = mode !== 'prompt'; input.value = mode === 'prompt' ? value : '';
    dialog.querySelectorAll('[data-app-dialog-cancel]').forEach(button => { button.hidden = mode === 'alert' && !button.classList.contains('ba-button--icon'); });
    const confirm = dialog.querySelector('[data-app-dialog-confirm]');
    confirm.textContent = mode === 'alert' ? '知道了' : danger ? '确认删除' : '确认';
    confirm.classList.toggle('ba-button--danger', danger);
    dialog.classList.toggle('ba-dialog--danger', danger);
    const tag = dialog.querySelector('[data-app-dialog-tag]');
    if (tag) tag.textContent = danger ? '请谨慎确认' : mode === 'prompt' ? '请输入' : mode === 'alert' ? '提示' : '请确认';
    const result = new Promise(resolve => { pending = { resolve, trigger, mode, closing: false }; });
    if (!dialog.open) dialog.showModal(); viewport();
    ui.surfaces.move(dialog, true);
    if (version === current) (mode === 'prompt' ? input : danger ? dialog.querySelector('[data-app-dialog-cancel]') : confirm).focus({ preventScroll: true });
    if (mode === 'prompt') input.scrollIntoView({ block: 'nearest' });
    return result;
  };
  dialog?.querySelectorAll('[data-app-dialog-cancel]').forEach(button => button.addEventListener('click', () => settle(cancelValue(pending)), options));
  dialog?.querySelector('[data-app-dialog-confirm]')?.addEventListener('click', () => settle(pending?.mode === 'prompt' ? dialog.querySelector('[data-app-dialog-input]').value.trim() : true), options);
  dialog?.addEventListener('cancel', event => { event.preventDefault(); settle(cancelValue(pending)); }, options);
  dialog?.addEventListener('keydown', event => {
    if (event.key === 'Enter' && event.target.matches('[data-app-dialog-input]') && !event.isComposing) { event.preventDefault(); settle(event.target.value.trim()); }
    if (event.key !== 'Tab') return;
    const controls = [...dialog.querySelectorAll('button,input')].filter(node => !node.hidden && !node.closest('[hidden]') && !node.disabled);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }, options);
  window.visualViewport?.addEventListener('resize', viewport, options);
  window.visualViewport?.addEventListener('scroll', viewport, options);
  window.addEventListener('resize', viewport, options);
  window.addEventListener('pagehide', reset, options);
  dialog?.addEventListener('close', () => { if (pending && !dialog.open) reset(); }, options);
  ui.dialogs = { request, confirm: (message, title, danger = false) => request({ message, title, danger }),
    prompt: (message, value = '', title) => request({ mode: 'prompt', message, value, title }),
    alert: (message, title) => request({ mode: 'alert', message, title }),
    destroy() { destroyed = true; reset(); lifecycle.abort(); } };
})();
