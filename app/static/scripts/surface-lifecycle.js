(() => {
  const ui = window.BakaUI = window.BakaUI || {};
  const states = new WeakMap(), active = new Set();
  let destroyed = false;
  const reduced = () => ui.motion.reduced();
  const stateFor = element => {
    let state = states.get(element);
    if (!state) { state = { animations: [], version: 0, done: null }; states.set(element, state); }
    return state;
  };
  const clear = element => {
    const state = states.get(element); if (!state) return;
    ++state.version;
    state.animations.forEach(animation => animation.cancel()); state.animations = [];
    state.done?.(false); state.done = null; active.delete(element);
    delete element.dataset.surfaceState;
  };
  const move = (element, open) => new Promise(resolve => {
    if (destroyed || !element?.isConnected) { resolve(false); return; }
    const state = stateFor(element), version = ++state.version;
    state.done?.(false); state.done = resolve; active.add(element);
    element.dataset.surfaceState = open ? 'entering' : 'leaving';
    const finish = () => {
      if (version !== state.version) return;
      state.animations.forEach(animation => animation.cancel()); state.animations = [];
      element.dataset.surfaceState = open ? 'visible' : 'closed';
      state.done = null; active.delete(element); resolve(true);
    };
    if (reduced() || !element.animate) { finish(); return; }
    if (!state.animations.length) {
      // 浮层只做透明度和位移，结束后不留变换。
      const frames = [{ opacity: 0, transform: 'translateY(10px)' }, { opacity: 1, transform: 'translateY(0)' }];
      const animation = element.animate(frames, { duration: 280, easing: 'cubic-bezier(.2,.78,.22,1)', fill: 'both' });
      animation.pause(); animation.currentTime = open ? 0 : 280;
      state.animations.push(animation);
    }
    state.animations.forEach(animation => { animation.playbackRate = open ? 1 : -1; animation.play(); });
    Promise.all(state.animations.map(animation => animation.finished)).then(finish, () => {});
  });
  const settleActive = () => {
    if (!reduced()) return;
    [...active].forEach(element => {
      const state = states.get(element), done = state.done;
      const open = element.dataset.surfaceState === 'entering';
      ++state.version; state.animations.forEach(animation => animation.cancel()); state.animations = [];
      state.done = null; active.delete(element); element.dataset.surfaceState = open ? 'visible' : 'closed'; done?.(true);
    });
  };
  const lifecycle = new AbortController();
  const observer = window.MutationObserver ? new MutationObserver(settleActive) : null;
  observer?.observe(document.documentElement, { attributes: true, attributeFilter: ['data-motion', 'data-performance'] });
  matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', settleActive, { signal: lifecycle.signal });
  window.addEventListener('pagehide', () => [...active].forEach(clear), { signal: lifecycle.signal });
  ui.surfaces = { move, clear, destroy() { destroyed = true; [...active].forEach(clear); observer?.disconnect(); lifecycle.abort(); } };
})();
