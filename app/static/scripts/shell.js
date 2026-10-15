(() => {
  // 常驻菜单：点菜单（以及页面里的普通链接）时，只替换页面内容，侧栏和底栏不重新加载，
  // 色块滑到新的位置、图标蹦一下；需要换菜单结构的跳转（登录、退出、后台）仍然整页打开。
  const ui = window.BakaUI = window.BakaUI || {};
  const root = document.documentElement;
  const main = document.getElementById('main-content');
  const header = document.querySelector('.site-header');
  const bar = document.querySelector('.mobile-bottom-nav');
  if (!main || !header || document.body.classList.contains('admin-body')
    || !window.fetch || !window.DOMParser || !window.history?.pushState) return;

  const lifecycle = new AbortController();
  const SKIP = /^\/(admin|bakaadmin|setup|media|api|static|healthz|readyz)(\/|$)|^\/auth\/(login|register|logout|gateway|callback|portal|avatar|status|recovery)(\/|$)/;
  const COVER = { stretch: 0.58, fade: 0.27, 'zoom-blur': 0.42, none: 0 };
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const reduced = () => (ui.motion ? ui.motion.reduced() : matchMedia('(prefers-reduced-motion: reduce)').matches);
  const transitionDuration = () => Math.max(300, Math.min(2400, Number.parseInt(root.dataset.transitionDuration, 10) || 720));
  const coverDelay = () => {
    if (reduced() || root.dataset.performance === 'low') return 0;
    return Math.round(transitionDuration() * (COVER[root.dataset.pageTransition] ?? COVER.stretch));
  };
  const keyOf = location_ => `${location_.pathname}${location_.search}`;
  const pathOf = raw => (raw || '').split('#')[0].split('?')[0];

  let controller = null, version = 0, currentKey = keyOf(location), enteringTimer = 0;
  const prefetched = new Map();

  // ---- 能不能局部换页 ----
  const eligible = (link, event) => {
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return null;
    if ((link.target && link.target !== '_self') || link.hasAttribute('download') || link.hasAttribute('data-shell-skip') || link.dataset.noTransition !== undefined) return null;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || !/^https?:$/.test(url.protocol)) return null;
    if (SKIP.test(url.pathname) || /\.[a-z0-9]{2,5}$/i.test(url.pathname)) return null;
    return url;
  };
  // 菜单结构一致（同一个登录状态、同样的菜单项）才可以只换内容。
  const navSignature = scope => [
    '.site-nav__links a', '.mobile-bottom-nav [data-mobile-nav-item]', '.drawer__links a',
  ].map(selector => [...scope.querySelectorAll(selector)].map(node => (node.hasAttribute('href') ? pathOf(node.getAttribute('href')) : 'button')).join('|')).join('#');
  const compatible = doc => Boolean(
    doc.getElementById('main-content') && doc.querySelector('.site-header') && doc.querySelector('.site-footer')
    && !doc.body.classList.contains('admin-body') && navSignature(doc) === navSignature(document),
  );

  // ---- 菜单状态 ----
  const setBarState = state => {
    if (!bar || !state) return;
    bar.dataset.navState = state;
    bar.querySelector('.mobile-bottom-nav__tabs')?.toggleAttribute('inert', state === 'cta');
    bar.querySelector('.mobile-bottom-nav__cta')?.toggleAttribute('inert', state !== 'cta');
  };
  const syncNav = doc => {
    ['.site-nav__links a', '.mobile-bottom-nav [data-mobile-nav-item]'].forEach(selector => {
      const theirs = [...doc.querySelectorAll(selector)];
      [...document.querySelectorAll(selector)].forEach((node, index) => {
        if (theirs[index]) node.classList.toggle('is-current', theirs[index].classList.contains('is-current'));
      });
    });
    setBarState(doc.querySelector('.mobile-bottom-nav')?.dataset.navState);
    ui.navigation?.syncCurrent();
  };
  // 点下去的那一刻，色块就开始滑、图标开始蹦，不等页面回来。
  const highlight = link => {
    const path = pathOf(link.getAttribute('href'));
    const scopes = [['.site-nav__links a'], ['.mobile-bottom-nav [data-mobile-nav-item]']];
    let hit = null;
    scopes.forEach(([selector]) => {
      const items = [...document.querySelectorAll(selector)];
      const match = items.find(node => node.hasAttribute('href') && pathOf(node.getAttribute('href')) === path);
      if (!match) return;
      items.forEach(node => node.classList.toggle('is-current', node === match));
      if (match.closest('.site-nav__links') ? matchMedia('(min-width: 861px)').matches : matchMedia('(max-width: 860px)').matches) hit = match;
    });
    ui.navigation?.syncCurrent();
    ui.navigation?.hop(hit || link);
  };

  // ---- 底栏：上划淡出缩回、下滑软软浮回 ----
  const mobile = matchMedia('(max-width: 860px)');
  let lastY = Math.max(0, scrollY), barHidden = false, scrollFrame = 0, remembered = 0;
  const setBarHidden = hidden => {
    if (!bar || barHidden === hidden) return;
    barHidden = hidden;
    bar.classList.toggle('is-bar-hidden', hidden);
  };
  const onScroll = () => {
    scrollFrame = 0;
    const y = Math.max(0, scrollY);
    const room = document.documentElement.scrollHeight - innerHeight;
    if (!mobile.matches || room < 48 || y < 48 || innerHeight + y >= document.documentElement.scrollHeight - 8
      || document.body.classList.contains('drawer-open') || bar?.contains(document.activeElement)) {
      setBarHidden(false); lastY = y; return;
    }
    const delta = y - lastY;
    if (delta > 10) { setBarHidden(true); lastY = y; }
    else if (delta < -10) { setBarHidden(false); lastY = y; }
  };
  window.addEventListener('scroll', () => {
    if (!scrollFrame) scrollFrame = requestAnimationFrame(onScroll);
    // 记住当前滚动位置，后退时可以回到原处。
    window.clearTimeout(remembered);
    remembered = window.setTimeout(() => {
      try { history.replaceState({ ...(history.state || {}), y: Math.round(scrollY) }, ''); } catch (_) { /* 记不住也没关系 */ }
    }, 120);
  }, { passive: true, signal: lifecycle.signal });
  mobile.addEventListener('change', () => setBarHidden(false), { signal: lifecycle.signal });
  bar?.addEventListener('focusin', () => setBarHidden(false), { signal: lifecycle.signal });

  // ---- 取页面 ----
  const fetchPage = (url, signal) => fetch(url, {
    signal, credentials: 'same-origin', headers: { 'X-Requested-With': 'bakashell', Accept: 'text/html' },
  }).then(async response => {
    const type = response.headers.get('content-type') || '';
    const finalUrl = new URL(response.url);
    if (!type.includes('text/html') || SKIP.test(finalUrl.pathname)) throw new Error('full-navigation');
    const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
    if (!compatible(doc)) throw new Error('full-navigation');
    return { doc, finalUrl };
  });
  const prefetch = link => {
    const url = eligible(link, { button: 0 });
    if (!url || keyOf(url) === currentKey) return;
    const key = url.href, cached = prefetched.get(key);
    if (cached && performance.now() - cached.at < 8000) return;
    const promise = fetchPage(url.href).catch(() => null);
    prefetched.set(key, { at: performance.now(), promise });
  };

  const hardNavigate = href => { root.classList.remove('is-page-leaving'); window.location.assign(href); };

  const swap = ({ doc, finalUrl }, push, y) => {
    window.dispatchEvent(new Event('baka:page-leave'));
    ui.motion?.beginSequence?.();
    document.title = doc.title;
    main.replaceChildren(...[...doc.getElementById('main-content').childNodes].map(node => document.importNode(node, true)));
    const footer = document.querySelector('.site-footer'), nextFooter = doc.querySelector('.site-footer');
    if (footer && nextFooter) footer.replaceWith(document.importNode(nextFooter, true));
    syncNav(doc);
    if (push) {
      try {
        history.replaceState({ ...(history.state || {}), y: Math.round(scrollY) }, '');
        history.pushState({ shell: true, y: 0 }, '', finalUrl.href);
      } catch (_) { hardNavigate(finalUrl.href); return; }
    }
    currentKey = keyOf(finalUrl);
    window.scrollTo(0, y || 0);
    lastY = y || 0; setBarHidden(false);
    root.classList.remove('is-page-leaving');
    if (!reduced() && root.dataset.pageTransition !== 'none') {
      root.classList.add('is-page-entering');
      window.clearTimeout(enteringTimer);
      enteringTimer = window.setTimeout(() => root.classList.remove('is-page-entering'), Math.max(1100, Math.round(transitionDuration() * 1.6)));
    }
    // 服务端放在这一页里的提示（保存成功之类），换页后照常弹出。
    doc.querySelectorAll('[data-toast-region] [data-toast]').forEach(toast => {
      const text = toast.textContent.replace('×', '').trim();
      if (text) ui.notifications?.notify(text, toast.dataset.toastCategory || 'info');
    });
    window.dispatchEvent(new Event('baka:page-ready'));
    ui.loadLine?.finish({ scope: main });
  };

  const go = async (url, { push = true, trigger = null, y = 0 } = {}) => {
    controller?.abort();
    controller = new AbortController();
    const mine = ++version;
    ui.loadLine?.start();
    if (trigger) highlight(trigger);
    if (document.body.classList.contains('drawer-open')) document.querySelector('[data-close-mobile-drawer]')?.click();
    setBarHidden(false);
    const cover = coverDelay();
    if (cover) root.classList.add('is-page-leaving');
    const started = performance.now();
    let result;
    try {
      const cached = prefetched.get(url.href);
      const cachedResult = cached && performance.now() - cached.at < 8000 ? await cached.promise : null;
      result = cachedResult || await fetchPage(url.href, controller.signal);
    } catch (error) {
      if (error?.name === 'AbortError' || mine !== version) return;
      hardNavigate(url.href);
      return;
    }
    if (mine !== version) return;
    const remaining = cover - (performance.now() - started);
    if (remaining > 0) await sleep(remaining);
    if (mine !== version) return;
    swap(result, push, y);
  };

  const visit = (href, options = {}) => {
    const url = new URL(href, location.href);
    if (url.origin !== location.origin || SKIP.test(url.pathname) || keyOf(url) === currentKey) return false;
    go(url, options);
    return true;
  };

  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[href]');
    const url = eligible(link, event);
    if (!url) return;
    // 同一页、只有锚点不同：交给浏览器；点当前菜单项：什么都不做。
    if (keyOf(url) === currentKey) return;
    event.preventDefault();
    go(url, { trigger: link.closest('.site-nav__links, .mobile-bottom-nav, .drawer__links') ? link : null });
  }, { capture: true, signal: lifecycle.signal });

  ['pointerenter', 'touchstart', 'focusin'].forEach(name => {
    document.addEventListener(name, event => {
      const link = event.target.closest?.('.site-nav__links a, .mobile-bottom-nav a, .drawer__links a');
      if (link) prefetch(link);
    }, { capture: true, passive: true, signal: lifecycle.signal });
  });

  window.addEventListener('popstate', event => {
    if (keyOf(location) === currentKey) return;
    go(new URL(location.href), { push: false, y: event.state?.y || 0 });
  }, { signal: lifecycle.signal });

  // 整页打开后又“后退”回来时，回到原来的滚动位置。
  try {
    history.scrollRestoration = 'manual';
    const entry = performance.getEntriesByType('navigation')[0];
    if (entry?.type === 'back_forward' && history.state?.y) window.scrollTo(0, history.state.y);
  } catch (_) { /* 不支持就用浏览器默认 */ }

  window.addEventListener('pageshow', event => { if (event.persisted) { controller?.abort(); root.classList.remove('is-page-leaving'); } }, { signal: lifecycle.signal });
  ui.shell = {
    visit,
    status: () => ({ key: currentKey, barHidden, prefetched: prefetched.size }),
    destroy() { controller?.abort(); lifecycle.abort(); },
  };
})();
