(() => {
  // 大数字：进入视口后从 0 数到真实数字。减少动态时直接显示真实数字。
  // 局部换页后会重新初始化：换页前停掉动画，换页后对新内容里的数字重新数。
  const ui = window.BakaUI = window.BakaUI || {};
  const lifecycle = new AbortController();
  const reduced = () => (ui.motion ? ui.motion.reduced() : matchMedia('(prefers-reduced-motion: reduce)').matches);
  const format = value => Math.round(value).toLocaleString('zh-CN');
  const DURATION = 1500, GAP = 140;
  const targetOf = element => Number.parseInt(element.dataset.countTo, 10);
  const show = element => { element.textContent = format(targetOf(element)); };

  let observer = null, frame = 0, elements = [];
  const running = new Set();
  const stop = () => {
    observer?.disconnect(); observer = null;
    if (frame) cancelAnimationFrame(frame);
    frame = 0; running.clear();
  };
  const settle = () => { const done = elements; stop(); done.forEach(element => { if (element.isConnected) show(element); }); };

  const tick = now => {
    running.forEach(job => {
      const progress = Math.min(1, Math.max(0, (now - job.start) / DURATION));
      const eased = 1 - Math.pow(1 - progress, 3);
      job.element.textContent = format(job.target * eased);
      if (progress >= 1) { job.element.textContent = format(job.target); running.delete(job); }
    });
    frame = running.size ? requestAnimationFrame(tick) : 0;
  };

  const init = () => {
    stop();
    elements = [...document.querySelectorAll('[data-count-to]')];
    if (!elements.length) return;
    if (reduced() || !('IntersectionObserver' in window) || !Element.prototype.animate) { elements.forEach(show); return; }
    let order = 0;
    const run = element => {
      const target = targetOf(element);
      if (!Number.isFinite(target) || target <= 0) { show(element); return; }
      running.add({ element, target, start: performance.now() + order * GAP });
      order += 1;
      if (!frame) frame = requestAnimationFrame(tick);
    };
    elements.forEach(element => { if (targetOf(element) > 0) element.textContent = '0'; });
    observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        run(entry.target);
      });
    }, { threshold: 0.4 });
    elements.forEach(element => observer.observe(element));
  };

  init();
  window.addEventListener('baka:page-leave', stop, { signal: lifecycle.signal });
  window.addEventListener('baka:page-ready', init, { signal: lifecycle.signal });
  // 页面离开或切后台回来时，保证显示的是真实数字。
  window.addEventListener('pagehide', settle, { signal: lifecycle.signal });
  window.addEventListener('pageshow', event => { if (event.persisted) settle(); }, { signal: lifecycle.signal });
  document.addEventListener('visibilitychange', () => { if (document.hidden && running.size) settle(); }, { signal: lifecycle.signal });
  ui.counters = { init, destroy() { settle(); lifecycle.abort(); } };
})();
