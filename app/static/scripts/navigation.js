(() => {
  const ui = window.BakaUI = window.BakaUI || {};
  let initialized = false;
  ui.navigation = { init() {
    if (initialized) return; initialized = true;
    const root = document.documentElement, body = document.body;
    const motionIsReduced = ui.motion.reduced;
    const bound = new Set(), timers = new Set(), frames = new Set();
    const listen = (target, name, callback, options) => {
      if (!target) return;
      target.addEventListener(name, callback, options);
      bound.add({target, name, callback, options});
    };
    const scheduleTimer = (callback, delay) => {
      const id = window.setTimeout(() => { timers.delete(id); callback(); }, delay);
      timers.add(id); return id;
    };
    const cancelTimer = id => { window.clearTimeout(id); timers.delete(id); };
    const scheduleFrame = callback => {
      const id = window.requestAnimationFrame(() => { frames.delete(id); callback(); });
      frames.add(id); return id;
    };
    const clearScheduled = () => {
      timers.forEach(id => window.clearTimeout(id)); timers.clear();
      frames.forEach(id => window.cancelAnimationFrame(id)); frames.clear();
      document.querySelectorAll('.is-height-animating').forEach(panel => {
        const record = adminAccordionTransitions.get(panel);
        if (record) panel.removeEventListener('transitionend', record.finish);
        adminAccordionTransitions.delete(panel);
        panel.classList.remove('is-height-animating'); panel.style.removeProperty('height');
      });
    };
  const mobileDrawer = document.querySelector("#mobile-drawer");
  const mobileBackdrop = document.querySelector("[data-mobile-backdrop]");
  const adminSidebar = document.querySelector("#admin-sidebar");
  const adminBackdrop = document.querySelector("[data-admin-backdrop]");
  let lastDrawerTrigger = null;
  let mobileDrawerState = "closed";
  let mobileDrawerCloseTimer = 0;
  let drawerVersion = 0;
  let mobileIndicatorTarget = null;
  let adminDrawerCloseTimer = 0;
  let adminDrawerVersion = 0;
  const mobileBottomNav = document.querySelector(".mobile-bottom-nav");
  const mobileNavIndicator = mobileBottomNav?.querySelector("[data-mobile-nav-indicator]");
  const currentMobileNavItem = () => mobileBottomNav?.querySelector("[data-mobile-nav-item].is-current");
  const moveMobileNavIndicator = (item, immediate = false) => {
    if (!mobileNavIndicator) return;
    mobileNavIndicator.style.opacity = item ? "" : "0";
    if (!item || !item.closest(".mobile-bottom-nav")) return;
    mobileIndicatorTarget = item;
    if (immediate) mobileNavIndicator.classList.add("is-immediate");
    mobileNavIndicator.style.width = `${item.offsetWidth}px`;
    mobileNavIndicator.style.height = `${item.offsetHeight}px`;
    mobileNavIndicator.style.transform = `translate3d(${item.offsetLeft}px,0,0)`;
    if (immediate) scheduleFrame(() => mobileNavIndicator.classList.remove("is-immediate"));
  };

  const focusableWithin = (container) => [
    ...container.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ];

  const setSiteInert = (value) => {
    document
      .querySelectorAll(".site-header, #main-content, .site-footer, .mobile-bottom-nav")
      .forEach((item) => {
        item.inert = value;
      });
  };

  const openMobileDrawer = (trigger) => {
    if (!mobileDrawer || !mobileBackdrop || mobileDrawerState === "open") return;
    cancelTimer(mobileDrawerCloseTimer);
    const version = ++drawerVersion;
    mobileDrawerState = "opening";
    mobileDrawer.inert = false;
    lastDrawerTrigger = trigger;
    mobileDrawer.setAttribute("aria-hidden", "false");
    mobileBackdrop.hidden = false;
    body.classList.add("drawer-open");
    document
      .querySelectorAll("[data-mobile-drawer]")
      .forEach((item) => item.setAttribute("aria-expanded", "true"));
    moveMobileNavIndicator(trigger);
    setSiteInert(true);
    scheduleFrame(() => {
      if (drawerVersion !== version) return;
      mobileDrawer.classList.add("is-open");
      mobileBackdrop.classList.add("is-visible");
      mobileDrawerState = "open";
      focusableWithin(mobileDrawer)[0]?.focus();
    });
  };

  const closeMobileDrawer = () => {
    if (!mobileDrawer || ["closed", "closing"].includes(mobileDrawerState)) return;
    cancelTimer(mobileDrawerCloseTimer);
    const version = ++drawerVersion;
    mobileDrawerState = "closing";
    mobileDrawer.inert = true;
    mobileDrawer.setAttribute("aria-hidden", "true");
    mobileDrawer.classList.remove("is-open");
    mobileBackdrop?.classList.remove("is-visible");
    document
      .querySelectorAll("[data-mobile-drawer]")
      .forEach((item) => item.setAttribute("aria-expanded", "false"));
    moveMobileNavIndicator(currentMobileNavItem());
    mobileDrawerCloseTimer = scheduleTimer(() => {
      if (drawerVersion !== version) return;
      setSiteInert(false);
      body.classList.remove("drawer-open");
      if (mobileBackdrop) mobileBackdrop.hidden = true;
      mobileDrawerState = "closed";
      lastDrawerTrigger?.focus();
    }, motionIsReduced() ? 0 : 360);
  };

  document.querySelectorAll("[data-mobile-drawer]").forEach((trigger) => {
    listen(trigger, "click", () => openMobileDrawer(trigger));
  });
  listen(document
    .querySelector("[data-close-mobile-drawer]"), "click", closeMobileDrawer);
  listen(mobileBackdrop, "click", closeMobileDrawer);
  moveMobileNavIndicator(currentMobileNavItem(), true);
  const refreshMobileIndicator = () => moveMobileNavIndicator(
    ["open", "opening"].includes(mobileDrawerState) ? mobileIndicatorTarget : currentMobileNavItem(),
  );
  listen(window, "resize", refreshMobileIndicator, { passive: true });
  listen(document, "keydown", (event) => {
    if (event.key === "Tab" && mobileDrawer?.classList.contains("is-open")) {
      const items = focusableWithin(mobileDrawer).filter((item) => item.offsetParent !== null);
      const first = items[0];
      const last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
    if (event.key === "Escape" && mobileDrawerState !== "closed") closeMobileDrawer();
  });

  listen(window, 
    "resize",
    () => {
      if (window.innerWidth > 860 && mobileDrawerState !== "closed") closeMobileDrawer();
    },
    { passive: true },
  );

  const openAdminDrawer = (trigger) => {
    if (!adminSidebar || !adminBackdrop) return;
    cancelTimer(adminDrawerCloseTimer);
    const version = ++adminDrawerVersion;
    lastDrawerTrigger = trigger;
    adminSidebar.classList.add("is-open");
    adminBackdrop.hidden = false;
    scheduleFrame(() => { if (adminDrawerVersion === version) adminBackdrop.classList.add("is-visible"); });
    trigger.setAttribute("aria-expanded", "true");
    body.classList.add("drawer-open");
    adminSidebar.querySelector("a")?.focus();
  };
  const closeAdminDrawer = () => {
    if (!adminSidebar) return;
    cancelTimer(adminDrawerCloseTimer);
    const version = ++adminDrawerVersion;
    adminSidebar.classList.remove("is-open");
    adminBackdrop?.classList.remove("is-visible");
    body.classList.remove("drawer-open");
    document.querySelector("[data-admin-drawer]")?.setAttribute("aria-expanded", "false");
    adminDrawerCloseTimer = scheduleTimer(() => { if (adminDrawerVersion === version && adminBackdrop) adminBackdrop.hidden = true; }, motionIsReduced() ? 0 : 180);
    lastDrawerTrigger?.focus();
  };
  listen(document.querySelector("[data-admin-drawer]"), "click", (event) => openAdminDrawer(event.currentTarget));
  listen(adminBackdrop, "click", closeAdminDrawer);
  listen(document, "keydown", (event) => {
    if (event.key === "Tab" && adminSidebar?.classList.contains("is-open")) {
      const items = focusableWithin(adminSidebar).filter((item) => item.offsetParent !== null);
      const first = items[0];
      const last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    if (event.key === "Escape" && adminSidebar?.classList.contains("is-open")) closeAdminDrawer();
  });
  listen(window, "resize", () => {
    if (window.innerWidth > 860 && adminSidebar?.classList.contains("is-open")) closeAdminDrawer();
  }, { passive: true });

  const capsuleNavigation = document.querySelector("[data-capsule-nav]");
  if (capsuleNavigation) {
    const capsuleViewport = window.matchMedia("(min-width: 621px)");
    let previousScrollY = Math.max(0, window.scrollY);
    let capsuleTicking = false;
    let arrivalTimer = 0;
    const pageCanScroll = () => document.documentElement.scrollHeight > window.innerHeight + 24;
    const setCapsuleVisible = (visible) => {
      capsuleNavigation.classList.toggle("is-nav-visible", visible);
      capsuleNavigation.classList.toggle("is-nav-hidden", !visible);
    };
    const updateCapsuleNavigation = () => {
      const currentScrollY = Math.max(0, window.scrollY);
      const scrollDelta = currentScrollY - previousScrollY;
      if (!capsuleViewport.matches || !pageCanScroll()) {
        setCapsuleVisible(true);
      } else if (scrollDelta > 0) {
        setCapsuleVisible(false);
      } else if (scrollDelta < 0) {
        setCapsuleVisible(true);
      }
      previousScrollY = currentScrollY;
      capsuleTicking = false;
    };
    const requestCapsuleUpdate = () => {
      if (capsuleTicking) return;
      capsuleTicking = true;
      scheduleFrame(updateCapsuleNavigation);
    };
    const resetCapsuleNavigation = () => {
      capsuleTicking = false;
      previousScrollY = Math.max(0, window.scrollY);
      setCapsuleVisible(true);
      requestCapsuleUpdate();
    };
    const playCapsuleArrival = () => {
      cancelTimer(arrivalTimer);
      capsuleNavigation.classList.remove("is-nav-arriving");
      if (capsuleViewport.matches && !motionIsReduced()) {
        scheduleFrame(() => capsuleNavigation.classList.add("is-nav-arriving"));
      }
      arrivalTimer = scheduleTimer(
        () => capsuleNavigation.classList.remove("is-nav-arriving"),
        680,
      );
    };
    setCapsuleVisible(true);
    if (!root.classList.contains("is-single-navigation")) playCapsuleArrival();
    listen(window, "scroll", requestCapsuleUpdate, { passive: true });
    listen(window, "resize", resetCapsuleNavigation, { passive: true });
    listen(capsuleViewport, "change", resetCapsuleNavigation);
    listen(window, "pageshow", (event) => {
      if (event.persisted) resetCapsuleNavigation();
    });
  }

  const navigationLinks = document.querySelector(".site-nav__links");
  let refreshDesktopIndicator = () => {};
  let syncDesktopIndicator = () => {};
  if (navigationLinks) {
    // 侧栏的色块只表示“现在在哪一页”：换页时用弹簧滑到新位置，悬停只让图标自己动。
    const indicator = document.createElement("span");
    indicator.className = "nav-indicator";
    indicator.setAttribute("aria-hidden", "true");
    navigationLinks.prepend(indicator);
    const currentLink = () => navigationLinks.querySelector("a.is-current");
    const moveIndicator = (link) => {
      indicator.classList.toggle("is-hidden", !link);
      if (!link) return;
      const linkRect = link.getBoundingClientRect();
      indicator.style.width = `${linkRect.width}px`;
      indicator.style.height = `${linkRect.height}px`;
      indicator.style.transform = `translate3d(${link.offsetLeft}px,${link.offsetTop}px,0)`;
    };
    refreshDesktopIndicator = () => moveIndicator(currentLink());
    syncDesktopIndicator = () => moveIndicator(currentLink());
    scheduleFrame(() => {
      indicator.style.transition = "none";
      moveIndicator(currentLink());
      scheduleFrame(() => { indicator.style.transition = ""; });
    });
    listen(window, "resize", refreshDesktopIndicator, { passive: true });
  }

  const adminNavigation = document.querySelector(".admin-nav");
  const adminAccordionTransitions = new WeakMap();
  const animateAdminAccordion = (items, nextItem, {
    panelSelector,
    toggleSelector,
    duration,
    ready,
  }) => {
    const records = items.map((item) => {
      const panel = item.querySelector(panelSelector);
      const open = item === nextItem;
      const changed = item.classList.contains("is-open") !== open;
      return {
        item,
        panel,
        open,
        changed,
        startHeight: changed ? (panel?.getBoundingClientRect().height || 0) : 0,
      };
    });
    const shouldAnimate = ready && !motionIsReduced();

    records.forEach(({ item, open }) => {
      item.classList.toggle("is-open", open);
      item.querySelector(toggleSelector)?.setAttribute("aria-expanded", String(open));
    });

    records.forEach(({ panel, open, changed, startHeight }) => {
      if (!panel) return;
      if (shouldAnimate && !changed) return;
      const previous = adminAccordionTransitions.get(panel);
      if (previous) {
        cancelTimer(previous.timer);
        panel.removeEventListener("transitionend", previous.finish);
      }
      if (!shouldAnimate) {
        panel.classList.remove("is-height-animating");
        panel.style.removeProperty("height");
        adminAccordionTransitions.delete(panel);
        return;
      }
      panel.classList.add("is-height-animating");
      panel.style.height = `${startHeight}px`;
      const endHeight = open ? panel.scrollHeight : 0;
      const token = {};
      const finish = (event) => {
        if (event && (event.target !== panel || event.propertyName !== "height")) return;
        if (adminAccordionTransitions.get(panel)?.token !== token) return;
        panel.classList.remove("is-height-animating");
        panel.style.removeProperty("height");
        panel.removeEventListener("transitionend", finish);
        cancelTimer(adminAccordionTransitions.get(panel)?.timer);
        adminAccordionTransitions.delete(panel);
      };
      panel.addEventListener("transitionend", finish);
      const timer = scheduleTimer(() => finish(), duration + 90);
      adminAccordionTransitions.set(panel, { token, timer, finish });
      scheduleFrame(() => {
        if (adminAccordionTransitions.get(panel)?.token === token) {
          panel.style.height = `${endHeight}px`;
        }
      });
    });
  };

  const adminMenuGroups = [...document.querySelectorAll("[data-admin-menu-group]")];
  if (adminNavigation && adminMenuGroups.length) {
    adminNavigation.dataset.heightAccordion = "true";
    let storedMenuKey = "";
    try { storedMenuKey = localStorage.getItem("cloudnest-admin-menu-open") || ""; } catch (_) { /* storage is optional */ }
    const currentGroup = adminMenuGroups.find((group) => group.querySelector(".is-current"));
    const storedGroup = adminMenuGroups.find((group) => group.dataset.menuKey === storedMenuKey);
    const initialGroup = currentGroup || storedGroup || adminMenuGroups.find((group) => group.dataset.menuKey === "dashboard");
    const setAdminMenuGroup = (nextGroup, persist = true) => {
      animateAdminAccordion(adminMenuGroups, nextGroup, {
        panelSelector: ":scope > .admin-nav-group__items",
        toggleSelector: ":scope > [data-admin-menu-toggle]",
        duration: 280,
        ready: adminNavigation.dataset.accordionReady === "true",
      });
      if (persist) {
        try { localStorage.setItem("cloudnest-admin-menu-open", nextGroup?.dataset.menuKey || ""); } catch (_) { /* storage is optional */ }
      }
    };
    setAdminMenuGroup(initialGroup, false);
    scheduleFrame(() => scheduleFrame(() => { adminNavigation.dataset.accordionReady = "true"; }));
    adminMenuGroups.forEach((group) => {
      listen(group.querySelector(":scope > [data-admin-menu-toggle]"), "click", () => {
        setAdminMenuGroup(group.classList.contains("is-open") ? null : group);
      });
    });
  }

  const routeTransitionKey = "cloudnest-route-transition";
  const singleNavigationKey = "cloudnest-single-navigation";
  let singleNavigationPending = false;
  let routeNavigationPending = false;
  const configuredTransitionDuration = () => Math.max(300, Math.min(2400, Number.parseInt(root.dataset.transitionDuration, 10) || 720));
  const routeTransitionDurations = () => {
    const duration = configuredTransitionDuration();
    return { stretch: Math.round(duration * 0.58), fade: Math.round(duration * 0.27), "zoom-blur": Math.round(duration * 0.42), none: 0 };
  };
  const currentTransitionStyle = () => routeTransitionDurations()[root.dataset.pageTransition] !== undefined ? root.dataset.pageTransition : "stretch";
  const beginPageLeave = (target) => {
    const style = currentTransitionStyle();
    if (motionIsReduced() || root.dataset.performance === "low" || style === "none") return 0;
    try { sessionStorage.setItem(routeTransitionKey, JSON.stringify({ startedAt: Date.now() })); } catch (_) { /* storage is optional */ }
    root.classList.add("is-page-leaving");
    return routeTransitionDurations()[style];
  };
  if (root.classList.contains("is-page-entering")) {
    scheduleTimer(() => root.classList.remove("is-page-entering"), Math.max(1100, Math.round(configuredTransitionDuration() * 1.6)));
  }
  if (root.classList.contains("is-single-navigation")) {
    scheduleFrame(() => root.classList.remove("is-single-navigation"));
  }
  listen(window, "pageshow", (event) => {
    singleNavigationPending = false;
    routeNavigationPending = false;
    root.classList.remove("is-page-leaving");
    if (event.persisted) root.classList.remove("is-page-entering");
    document.querySelectorAll("form[data-transition-submitting]").forEach(form => delete form.dataset.transitionSubmitting);
  });

  listen(document, "click", (event) => {
    const link = event.target.closest("a[href]");
    if (
      !link ||
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      link.target === "_blank" ||
      link.hasAttribute("download") ||
      link.dataset.noTransition !== undefined
    ) {
      return;
    }
    const target = new URL(link.href, window.location.href);
    if (target.origin !== window.location.origin || !["http:", "https:"].includes(target.protocol)) return;
    const sameLocation = (
      target.pathname === window.location.pathname
      && target.search === window.location.search
    );
    const usesSingleNavigation = Boolean(link.closest("[data-single-navigation]"));
    if (sameLocation) {
      if (usesSingleNavigation && !target.hash) event.preventDefault();
      return;
    }
    if (usesSingleNavigation) {
      event.preventDefault();
      if (singleNavigationPending || routeNavigationPending) return;
      singleNavigationPending = true;
      try {
        sessionStorage.removeItem(routeTransitionKey);
        sessionStorage.setItem(singleNavigationKey, JSON.stringify({ startedAt: Date.now() }));
      } catch (_) { /* storage is optional */ }
      window.location.assign(target.href);
      return;
    }
    const delay = beginPageLeave(target);
    if (!delay) return;
    event.preventDefault();
    if (routeNavigationPending || singleNavigationPending) return;
    routeNavigationPending = true;
    scheduleTimer(() => window.location.assign(target.href), delay);
  });

  listen(document, "submit", (event) => {
    const form = event.target;
    // Identity submits once natively; its busy guard must not block a deferred resubmit.
    if (form.matches('[data-auth-form]')) return;
    if (event.defaultPrevented || form.dataset.transitionSubmitting === "true" || (!form.noValidate && !form.checkValidity()) || form.target === "_blank") return;
    const target = new URL(form.action || window.location.href, window.location.href);
    if (target.origin !== window.location.origin) return;
    const delay = beginPageLeave(target);
    if (!delay) return;
    event.preventDefault();
    if (routeNavigationPending || singleNavigationPending) return;
    routeNavigationPending = true;
    const submitter = event.submitter;
    scheduleTimer(() => {
      form.dataset.transitionSubmitting = "true";
      if (submitter?.isConnected) form.requestSubmit(submitter);
      else form.requestSubmit();
    }, delay);
  });

  document.querySelectorAll("[data-identity-menu]").forEach((menu) => {
    const trigger = menu.querySelector("[data-identity-menu-trigger]");
    const panel = menu.querySelector("[data-identity-menu-panel]");
    const setOpen = (open) => {
      menu.classList.toggle("is-open", open);
      trigger?.setAttribute("aria-expanded", String(open));
    };
    listen(trigger, "click", (event) => {
      event.stopPropagation();
      setOpen(!menu.classList.contains("is-open"));
    });
    listen(menu, "mouseenter", () => setOpen(true));
    listen(document, "pointermove", (event) => {
      if (!menu.classList.contains("is-open") || menu.matches(":focus-within")) return;
      const triggerRect = trigger?.getBoundingClientRect();
      const panelRect = panel?.getBoundingClientRect();
      if (!triggerRect || !panelRect) return;
      const insideTrigger =
        event.clientX >= triggerRect.left &&
        event.clientX <= triggerRect.right &&
        event.clientY >= triggerRect.top &&
        event.clientY <= triggerRect.bottom;
      const insidePanel =
        event.clientX >= panelRect.left &&
        event.clientX <= panelRect.right &&
        event.clientY >= panelRect.top &&
        event.clientY <= panelRect.bottom;
      const insideDownwardBridge =
        event.clientX >= triggerRect.left - 5 &&
        event.clientX <= triggerRect.right + 5 &&
        event.clientY > triggerRect.bottom &&
        event.clientY < panelRect.top;
      // 侧栏里菜单从头像旁边弹出：触发器与面板之间的横向空隙也算在内。
      const insideSideBridge =
        event.clientX >= Math.min(triggerRect.right, panelRect.right) - 1 &&
        event.clientX <= Math.max(triggerRect.left, panelRect.left) + 1 &&
        event.clientY >= Math.min(triggerRect.top, panelRect.top) &&
        event.clientY <= Math.max(triggerRect.bottom, panelRect.bottom);
      if (!insideTrigger && !insidePanel && !insideDownwardBridge && !insideSideBridge) setOpen(false);
    });
    listen(menu, "keydown", (event) => {
      if (event.key === "Escape") {
        setOpen(false);
        trigger?.blur();
      }
    });
    listen(menu, "focusout", () =>
      scheduleTimer(() => {
        if (!menu.matches(":focus-within")) setOpen(false);
      }, 0),
    );
    listen(document, "click", (event) => {
      if (!menu.contains(event.target)) setOpen(false);
    });
  });


    const geometryTargets = [...document.querySelectorAll('.site-nav__links, .site-nav__links a, .mobile-bottom-nav, [data-mobile-nav-item]')];
    const resize = 'ResizeObserver' in window ? new ResizeObserver(() => {
      refreshMobileIndicator(); refreshDesktopIndicator();
    }) : null;
    geometryTargets.forEach(node => resize?.observe(node));
    document.fonts?.ready.then(() => { if (initialized) { refreshMobileIndicator(); refreshDesktopIndicator(); } });
    const resetTransient = () => {
      drawerVersion++; adminDrawerVersion++; mobileDrawerState = 'closed';
      mobileDrawer?.classList.remove('is-open');
      if (mobileDrawer) { mobileDrawer.inert = true; mobileDrawer.setAttribute('aria-hidden','true'); }
      if (mobileBackdrop) { mobileBackdrop.hidden = true; mobileBackdrop.classList.remove('is-visible'); }
      if (adminBackdrop) { adminBackdrop.hidden = true; adminBackdrop.classList.remove('is-visible'); }
      adminSidebar?.classList.remove('is-open'); body.classList.remove('drawer-open'); setSiteInert(false);
      document.querySelectorAll('[data-mobile-drawer], [data-admin-drawer]').forEach(node => node.setAttribute('aria-expanded','false'));
      singleNavigationPending = false; routeNavigationPending = false;
      capsuleNavigation?.classList.remove('is-nav-arriving');
      mobileNavIndicator?.classList.remove('is-immediate');
      root.classList.remove('is-page-leaving','is-page-entering');
      refreshMobileIndicator(); refreshDesktopIndicator();
    };
    listen(window, 'pagehide', () => { clearScheduled(); resize?.disconnect(); resetTransient(); });
    listen(window, 'pageshow', event => {
      if (event.persisted) { resetTransient(); geometryTargets.forEach(node => resize?.observe(node)); }
    });
    ui.navigation.destroy = () => {
      clearScheduled(); resize?.disconnect(); resetTransient();
      bound.forEach(({target,name,callback,options}) => target.removeEventListener(name,callback,options)); bound.clear();
      navigationLinks?.querySelector('.nav-indicator')?.remove(); initialized = false;
    };
    ui.navigation.status = () => ({ drawer: mobileDrawerState, timers: timers.size, frames: frames.size,
      singleNavigationPending, routeNavigationPending });
    ui.navigation.beginPageLeave = beginPageLeave;
    // 常驻菜单：局部换页后只同步“当前项”，让色块滑过去；点中的菜单项图标蹦一下。
    ui.navigation.syncCurrent = () => { moveMobileNavIndicator(currentMobileNavItem()); syncDesktopIndicator(); };
    ui.navigation.hop = (node) => {
      if (!node || motionIsReduced()) return;
      node.classList.remove("is-hopping"); void node.offsetWidth; node.classList.add("is-hopping");
      scheduleTimer(() => node.classList.remove("is-hopping"), 620);
    };
  } };
})();
