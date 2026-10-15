(() => {
  const requests = new Map();
  document.addEventListener('submit', async event => {
    const form = event.target.closest('[data-favorite-form]'); if (!form) return;
    event.preventDefault(); if (requests.has(form)) return;
    const button = form.querySelector('button'), error = form.querySelector('[data-favorite-error]');
    const controller = new AbortController(); requests.set(form, controller);
    const body = new FormData(form); body.set('favorite_state', form.dataset.favoriteState);
    const idleLabel = button.textContent;
    button.textContent = '正在保存…';
    button.disabled = true; button.setAttribute('aria-busy', 'true'); error.hidden = true;
    try {
      const response = await fetch(form.action, { method: 'POST', body, signal: controller.signal,
        headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' }, credentials: 'same-origin' });
      const payload = await response.json();
      if (!response.ok || !payload.ok || typeof payload.is_favorite !== 'boolean') throw Error('failed');
      if (controller.signal.aborted || !form.isConnected) return;
      form.dataset.favoriteState = payload.is_favorite ? 'remove' : 'add';
      button.textContent = payload.is_favorite ? '移出收藏' : '收藏图片';
      button.classList.toggle('ba-button--soft', payload.is_favorite);
      window.BakaUI.notifications.notify(payload.is_favorite ? '已收藏图片。' : '已移出收藏。', 'success');
      const tile = form.closest('.favorite-tile');
      if (tile && !payload.is_favorite) {
        const next = (tile.nextElementSibling?.matches('.favorite-tile') && tile.nextElementSibling.querySelector('a'))
          || (tile.previousElementSibling?.matches('.favorite-tile') && tile.previousElementSibling.querySelector('a'))
          || document.querySelector('.favorites-hero__discover');
        next?.focus({ preventScroll: true });
        if (!window.BakaUI.motion.reduced() && tile.animate) {
          try { await tile.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 220, easing: 'ease-out' }).finished; } catch (_) {}
        }
        if (controller.signal.aborted) return;
        tile.remove();
        const count = document.querySelector('[data-favorites-count]');
        if (count) count.textContent = document.querySelectorAll('.favorite-tile').length + ' 张喜欢的图片';
        const empty = document.querySelector('[data-favorites-empty]');
        if (empty && !document.querySelector('.favorite-tile')) { empty.hidden = false; window.BakaUI.motion.prepare(empty); }
      }
    } catch (failure) {
      if (!controller.signal.aborted) { button.textContent = idleLabel; error.hidden = false; error.textContent = '未能保存，请再试一次。'; }
    } finally {
      if (requests.get(form) === controller) { requests.delete(form); button.disabled = false; button.setAttribute('aria-busy', 'false'); }
    }
  });
  window.addEventListener('pagehide', () => {
    requests.forEach((controller, form) => {
      controller.abort(); const button = form.querySelector('button'); button.disabled = false; button.setAttribute('aria-busy','false');
      if (form.dataset.favoriteState === 'add') form.closest('.favorite-tile')?.remove();
    }); requests.clear();
    const empty = document.querySelector('[data-favorites-empty]');
    if (empty && !document.querySelector('.favorite-tile')) empty.hidden = false;
  });
})();
