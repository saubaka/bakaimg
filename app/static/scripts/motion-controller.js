(() => {
  const ui = window.BakaUI = window.BakaUI || {};
  const root = document.documentElement;
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  const records = new WeakMap();
  const mounted = new Set();
  const listeners = new AbortController();

  // 一套入场/出场：只做透明度和位移，结束后不留变换，也没有 fill: forwards。
  // 页面载入时按文档顺序依次入场；滚动时每个元素进入视口入场、离开视口出场，再回来会重播。
  // 容器（卡片、面板）先动，里面的文字和按钮稍后依次跟上。
  const BLOCKS = [
    '.card', '.ba-panel', '.ba-stat', '.ba-empty', '.ba-tabs', '.ba-table tbody tr',
    '.tile', '.bento-card', '.square-card', '.stat-figure', '.stat-chart', '.info-card', '.faq', '.cta-card', '.photo-window',
    '.album-choice', '.album-order article', '.favorite-tile', '.auth-card', '.policy-card',
    '.token-reveal', '.token-list > *', '.share-stage', '.image-stage', '.share-side',
    '.upload-stage', '.page-head', '.section-head', '.site-footer',
    // 后台：页顶、版块标题、各类设置卡、表格表头、时间线与事件列表
    '.admin-topbar', '.section-heading', '.ba-block', '.role-card', '.editor-card', '.transition-choice',
    '.transition-duration-card', '.appearance-color-card', '.gateway-connection-card',
    '.gateway-binding-card', '.setting-toggle', '.ba-table thead', '.event-list > *', '.timeline-list > *',
    '.metric-grid > *', '.role-fieldset', '.storage-metrics > *', '.storage-users > *',
    '[data-reveal]',
  ];
  const TEXT = [
    'h1', 'h2', 'h3', '.ba-lead', '.page-head__meta', '.form-footnote', '.auth-secondary',
    '.security-note', 'legend', '.faq p', '.policy-card p', '.policy-card li', '.home-hero__facts li',
    '.bento-card p', '.bento-card pre', '.mini-list li', '.info-card strong', '.info-card p', '.tile__body',
    '.ba-stat__body', '.ba-empty p', '.cta-card p', '#main-content p',
    '.ba-table__who', '.ba-table td > strong', '.role-card p', '.editor-card p', '.muted',
  ];
  const CONTROLS = [
    '.ba-button', '.ba-field', '.check-field', '.copy-field', '.ba-badge', '.chip-row', '.search-form',
    '.ba-avatar', '.admin-thumb', '.quota-meter', '.ba-select', '.ba-input',
  ];
  // 固定界面（导航、菜单、弹窗、提示）不参与滚动动画。
  const FIXED = '.site-header, .mobile-bottom-nav, .mobile-drawer, .drawer-backdrop, .toast-region, '
    + '.ba-dialog, .app-system-dialog, .identity-menu, .upload-visibility__menu, .ba-rail, .admin-sidebar, '
    + '.media-frame__error, .admin-menu-button, [data-no-motion]';
  const NAMED_BLOCKS = BLOCKS.filter(item => item !== '[data-reveal]').join(',');
  const SELECTOR = [...BLOCKS, ...TEXT, ...CONTROLS].join(',');
  const selector = () => SELECTOR;

  const STAGGER = 70, MAX_DELAY = 700, CHILD_GAP = 45, CHILD_LEAD = 110, CHILD_CAP = 420;
  const DURATION = 520, EXIT_DURATION = 260, DISTANCE = 16, EXIT_DISTANCE = 10;
  const EASE = 'cubic-bezier(.2,.78,.22,1)';
  let observer = null, mutations = null, suspended = false, pending = [], flushFrame = 0, firstFlush = true;

  const reduced = () => root.dataset.motion === 'reduce' || root.dataset.performance === 'low'
    || (root.dataset.motion !== 'full' && media.matches) || !Element.prototype.animate;
  const visible = element => {
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && rect.top < innerHeight * .94 && rect.bottom > 0;
  };
  const isRow = element => element.matches('tr');
  const managedParent = element => element.parentElement?.closest('[data-motion-managed]') || null;
  const routeLead = () => {
    if (!root.classList.contains('is-page-entering')) return 0;
    return (Number.parseInt(getComputedStyle(root).getPropertyValue('--route-content-delay'), 10) || 115) + 80;
  };

  const finish = (element, record) => {
    record.animation = null;
    element.classList.remove('is-motion-pending');
    element.classList.add('is-revealed');
    element.dataset.motionState = 'settled';
  };
  const settle = element => {
    const record = records.get(element);
    if (!record) return;
    record.animation?.cancel();
    record.shown = true;
    observer?.unobserve(element);
    finish(element, record);
  };

  // 入场：from 为 -1 表示从上方进入（向上滚动），1 表示从下方进入。
  const enter = (element, delay, from = 1) => {
    const record = records.get(element);
    if (!record || record.shown || suspended) return;
    record.shown = true;
    record.delay = delay;
    record.animation?.cancel();
    if (reduced() || element.contains(document.activeElement)) { finish(element, record); return; }
    element.classList.remove('is-motion-pending');
    element.dataset.motionState = 'entering';
    try {
      record.animation = element.animate(
        [{ opacity: 0, transform: `translateY(${DISTANCE * from}px)` }, { opacity: 1, transform: 'translateY(0)' }],
        { duration: DURATION, delay, easing: EASE, fill: 'backwards' },
      );
      record.animation.finished.then(() => finish(element, record)).catch(() => {});
    } catch (_) { finish(element, record); }
  };

  // 出场：离开视口时淡出并朝离开的方向挪一点；结束后回到“待入场”，再次进入会重播入场。
  const leave = (element, toward) => {
    const record = records.get(element);
    if (!record || !record.shown || suspended || reduced()) return;
    if (element.contains(document.activeElement)) return;
    record.shown = false;
    record.animation?.cancel();
    element.dataset.motionState = 'leaving';
    const park = () => {
      if (record.shown) return;
      record.animation = null;
      element.classList.remove('is-revealed');
      element.classList.add('is-motion-pending');
      element.dataset.motionState = 'idle';
    };
    try {
      record.animation = element.animate(
        [{ opacity: 1, transform: 'translateY(0)' }, { opacity: 0, transform: `translateY(${EXIT_DISTANCE * toward}px)` }],
        { duration: EXIT_DURATION, easing: 'ease-in', fill: 'backwards' },
      );
      // 先把最终状态（透明）写进样式，再结束动画，避免闪回。
      element.classList.add('is-motion-pending');
      record.animation.finished.then(park).catch(() => {});
    } catch (_) { park(); }
  };

  const flush = () => {
    flushFrame = 0;
    const batch = pending.filter(item => item.element.isConnected && records.has(item.element));
    pending = [];
    batch.sort((a, b) => (a.element.compareDocumentPosition(b.element) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
    const lead = firstFlush ? routeLead() : 0;
    firstFlush = false;
    let top = 0;
    const children = new Map();
    batch.forEach(({ element, from }) => {
      const parent = managedParent(element);
      const parentRecord = parent && records.get(parent);
      let delay;
      if (parentRecord && typeof parentRecord.delay === 'number' && !isRow(element)) {
        const nth = children.get(parent) || 0;
        children.set(parent, nth + 1);
        delay = Math.min(parentRecord.delay + CHILD_LEAD + nth * CHILD_GAP, parentRecord.delay + CHILD_CAP);
      } else {
        delay = lead + Math.min(top * STAGGER, MAX_DELAY);
        top += 1;
      }
      enter(element, delay, from);
    });
  };
  const queue = (element, from = 1) => {
    const existing = pending.find(item => item.element === element);
    if (existing) existing.from = from;
    else pending.push({ element, from });
    if (!flushFrame) flushFrame = requestAnimationFrame(flush);
  };

  const register = element => {
    if (!element.isConnected || records.has(element)) return;
    if (element.closest(FIXED)) return;
    // 只包着别的动画元素的容器自己不动，让里面的内容各自依次入场。
    if (element.matches('[data-reveal]') && !element.matches(NAMED_BLOCKS) && element.querySelector(selector())) return;
    // 版块标题、页头里的文字由所在容器带着入场。
    if (element.matches(TEXT.concat(CONTROLS).join(','))
      && element.closest('.page-head, .section-head, .section-heading, .admin-topbar')
      && !element.matches('.ba-button')) return;
    // 输入框、选择框已经在 .ba-field 里，跟着字段一起动。
    if (element.matches('.ba-input, .ba-select') && element.closest('.ba-field')) return;
    if (element.matches('.ba-avatar, .admin-thumb') && element.closest('tr, .ba-block, .ba-stat')) return;
    const record = { animation: null, shown: false, delay: null };
    records.set(element, record);
    mounted.add(element);
    element.setAttribute('data-motion-managed', '');
    if (element.matches('.card, .ba-panel')) element.setAttribute('data-card-motion', '');
    if (reduced()) { settle(element); return; }
    element.classList.add('is-motion-pending');
    element.dataset.motionState = 'idle';
    if (observer) observer.observe(element);
    else if (visible(element)) queue(element);
  };
  const prepare = (scope = document) => {
    const candidates = [...scope.querySelectorAll(selector())];
    if (scope instanceof Element && scope.matches(selector())) candidates.unshift(scope);
    candidates.forEach(register);
  };
  const release = element => {
    const record = records.get(element);
    if (!record) return;
    record.animation?.cancel();
    observer?.unobserve(element);
    records.delete(element);
    mounted.delete(element);
    element.removeAttribute('data-motion-managed');
    delete element.dataset.motionState;
    element.classList.remove('is-motion-pending');
    element.classList.add('is-revealed');
  };
  const preferencesChanged = () => { if (reduced()) mounted.forEach(settle); };

  const connect = () => {
    if ('IntersectionObserver' in window) {
      observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          const bounds = entry.rootBounds || { top: 0, bottom: innerHeight };
          const above = entry.boundingClientRect.bottom <= bounds.top + 1;
          const below = entry.boundingClientRect.top >= bounds.bottom - 1;
          // 跨在上边缘说明是向上滚动时从上方进入，其余从下方进入。
          if (entry.isIntersecting) queue(entry.target, entry.boundingClientRect.top < bounds.top ? -1 : 1);
          else if (above) leave(entry.target, -1);
          else if (below) leave(entry.target, 1);
        });
      }, { threshold: 0, rootMargin: '-4% 0px -5% 0px' });
    } else {
      // 没有观察器时，滚动时逐个检查（只入场，不出场）。
      window.addEventListener('scroll', () => mounted.forEach(element => {
        if (!records.get(element)?.shown && visible(element)) queue(element);
      }), { passive: true, signal: listeners.signal });
    }
    // 滚到页面底部时，贴着底边而没能越过观察线的元素也要显示出来。
    let rescue = 0;
    window.addEventListener('scroll', () => {
      if (rescue || suspended) return;
      rescue = requestAnimationFrame(() => {
        rescue = 0;
        if (innerHeight + scrollY < document.documentElement.scrollHeight - 4) return;
        mounted.forEach(element => { if (!records.get(element)?.shown && visible(element)) queue(element); });
      });
    }, { passive: true, signal: listeners.signal });
    mutations = new MutationObserver(entries => {
      for (const element of mounted) if (!element.isConnected) release(element);
      entries.forEach(entry => entry.addedNodes.forEach(node => { if (node instanceof Element) prepare(node); }));
    });
    mutations.observe(root, { childList: true, subtree: true });
    const preferences = new MutationObserver(preferencesChanged);
    preferences.observe(root, { attributes: true, attributeFilter: ['data-motion', 'data-performance'] });
    ui.motionPreferencesObserver = preferences;
    media.addEventListener('change', preferencesChanged, { signal: listeners.signal });
    document.addEventListener('focusin', event => {
      for (const element of mounted) if (element.contains(event.target)) settle(element);
    }, { signal: listeners.signal });
    window.addEventListener('pagehide', () => {
      suspended = true;
      cancelAnimationFrame(flushFrame);
      flushFrame = 0;
      pending = [];
      mounted.forEach(settle);
    }, { signal: listeners.signal });
    window.addEventListener('pageshow', event => { if (event.persisted) suspended = false; }, { signal: listeners.signal });
  };
  connect();
  ui.motion = {
    prepare,
    release,
    reduced,
    // 局部换页后，新内容的第一屏要像刚打开页面一样依次入场。
    beginSequence() { firstFlush = true; },
    destroy() {
      suspended = true;
      cancelAnimationFrame(flushFrame);
      flushFrame = 0;
      listeners.abort();
      observer?.disconnect();
      mutations?.disconnect();
      ui.motionPreferencesObserver?.disconnect();
      [...mounted].forEach(release);
    },
    // 只读诊断：不含用户数据，用来确认清理是否干净。
    inspect(element) {
      const record = records.get(element);
      return record ? { state: element.dataset.motionState, animating: Boolean(record.animation), done: record.shown } : null;
    },
    stats() { return { mounted: mounted.size, queued: pending.length, driver: observer ? 'intersection' : 'scroll', suspended }; },
  };
})();
