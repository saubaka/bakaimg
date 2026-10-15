(() => {
  const lifecycle = new AbortController();
  document.querySelectorAll('[data-password-toggle]').forEach(button => {
    const input = document.getElementById(button.getAttribute('aria-controls')); if (!input) return;
    button.hidden = false;
    button.addEventListener('click', () => {
      const visible = input.type === 'password'; input.type = visible ? 'text' : 'password';
      button.setAttribute('aria-pressed', String(visible)); button.textContent = visible ? '隐藏' : '显示';
      button.setAttribute('aria-label', (visible ? '隐藏' : '显示') + input.closest('.ba-field').querySelector('[data-field-label]').textContent);
    }, { signal: lifecycle.signal });
  });
  document.querySelectorAll('[data-auth-form] .ba-field input').forEach(input => input.addEventListener('input', () => {
    if (input.getAttribute('aria-invalid') !== 'true') return;
    input.setAttribute('aria-invalid', 'false');
    const message = document.getElementById(input.getAttribute('aria-describedby')); if (message) message.textContent = '';
  }, { signal: lifecycle.signal }));
  const unlock = () => document.querySelectorAll('[data-auth-form]').forEach(form => {
    delete form.dataset.submitting;
    const button = form.querySelector('[type="submit"]'); button.disabled = false; button.removeAttribute('aria-busy');
    if (button.dataset.idleLabel) { button.textContent = button.dataset.idleLabel; delete button.dataset.idleLabel; }
  });
  document.querySelectorAll('[data-auth-form]').forEach(form => form.addEventListener('submit', event => {
    if (form.dataset.submitting === 'true') { event.preventDefault(); return; }
    form.dataset.submitting = 'true';
    const button = form.querySelector('[type="submit"]'); button.disabled = true; button.setAttribute('aria-busy', 'true');
    if (button.dataset.busyLabel) { button.dataset.idleLabel = button.textContent; button.textContent = button.dataset.busyLabel; }
  }, { signal: lifecycle.signal }));
  window.addEventListener('pagehide', () => {
    unlock(); document.querySelectorAll('[data-password-toggle]').forEach(button => {
      document.getElementById(button.getAttribute('aria-controls')).type = 'password'; button.textContent = '显示'; button.setAttribute('aria-pressed','false');
      button.setAttribute('aria-label', '显示' + button.closest('.ba-field').querySelector('[data-field-label]').textContent);
    });
  }, { signal: lifecycle.signal });
  window.addEventListener('pageshow', unlock, { signal: lifecycle.signal });
  window.BakaUI.auth = { destroy() { unlock(); lifecycle.abort(); } };
})();
