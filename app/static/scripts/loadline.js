(() => {
  // 页面加载线：载入时（以及局部换页时）顶部出现一条浅色细线，
  // 等页面、字体和首屏图片都加载完，才让它走完并带着动画收起来。
  const ui = window.BakaUI = window.BakaUI || {};
  const root = document.documentElement;
  const MINIMUM = 520, GIVE_UP = 12000, FINISH = 520, LEAVE = 360;
  const timers = new Set();
  let startedAt = performance.now(), version = 0, finishing = -1, active = root.classList.contains('is-loading');

  const later = (callback, delay) => {
    const id = setTimeout(() => { timers.delete(id); callback(); }, delay);
    timers.add(id);
    return id;
  };
  const clear = () => { timers.forEach(clearTimeout); timers.clear(); };
  const wait = delay => new Promise(resolve => later(resolve, delay));
  const reducedLine = () => root.dataset.motion === 'reduce' || root.dataset.performance === 'low'
    || (root.dataset.motion !== 'full' && matchMedia('(prefers-reduced-motion: reduce)').matches);

  // 首屏附近的图片框都有了结果（加载好或出错）才算加载完。
  const settled = frame => frame.classList.contains('is-ready') || frame.classList.contains('is-error');
  const mediaSettled = scope => new Promise(resolve => {
    const waiting = () => [...scope.querySelectorAll('[data-media-frame]')].filter(frame => {
      const rect = frame.getBoundingClientRect();
      return rect.width > 0 && rect.bottom > -120 && rect.top < innerHeight + 240 && !settled(frame);
    });
    const check = () => (waiting().length ? later(check, 90) : resolve());
    check();
  });
  const loaded = () => (document.readyState === 'complete'
    ? Promise.resolve()
    : new Promise(resolve => window.addEventListener('load', resolve, { once: true })));

  const reset = () => {
    root.classList.remove('is-loading', 'is-finishing', 'is-line-leaving');
    root.classList.add('has-loaded');
    active = false;
  };
  const start = () => {
    clear(); version += 1;
    root.classList.remove('is-finishing', 'is-line-leaving');
    void root.offsetWidth;
    root.classList.add('is-loading');
    startedAt = performance.now(); active = true;
    later(() => finish({ force: true }), GIVE_UP);
  };
  const finish = async ({ scope = document, force = false } = {}) => {
    if (!active || (!force && finishing === version)) return;
    const mine = version;
    finishing = version;
    if (!force) {
      await loaded();
      await Promise.race([document.fonts?.ready || Promise.resolve(), wait(2500)]);
      await mediaSettled(scope);
    }
    if (mine !== version || !active) return;
    await wait(Math.max(0, MINIMUM - (performance.now() - startedAt)));
    if (mine !== version || !active) return;
    if (reducedLine()) { reset(); return; }
    root.classList.add('is-finishing');
    await wait(FINISH);
    if (mine !== version || !active) return;
    root.classList.add('is-line-leaving');
    await wait(LEAVE);
    if (mine !== version || !active) return;
    reset();
  };

  if (active) { later(() => finish({ force: true }), GIVE_UP); finish(); }
  window.addEventListener('pageshow', event => { if (event.persisted) { clear(); reset(); } });
  ui.loadLine = { start, finish, status: () => ({ active, version }) };
})();
