(() => {
  const key = "cloudnest-route-transition";
  const singleNavigationKey = "cloudnest-single-navigation";
  const root = document.documentElement;
  const duration = Math.max(300, Math.min(2400, Number.parseInt(root.dataset.transitionDuration, 10) || 720));
  const safeColor = (value, fallback) => /^#[0-9a-f]{6}$/i.test(value || "") ? value : fallback;
  const timing = {
    "--route-duration": duration,
    "--route-stretch-cover": Math.round(duration * 0.58),
    "--route-stretch-reveal": Math.round(duration * 0.86),
    "--route-fade-cover": Math.round(duration * 0.27),
    "--route-fade-reveal": Math.round(duration * 0.46),
    "--route-focus-cover": Math.round(duration * 0.42),
    "--route-focus-reveal": Math.round(duration * 0.69),
    "--route-reveal-delay": Math.round(duration * 0.08),
    "--route-content-delay": Math.round(duration * 0.16),
  };
  Object.entries(timing).forEach(([name, value]) => root.style.setProperty(name, `${value}ms`));
  const colors = {
    "--route-color-start": safeColor(root.dataset.transitionColorStart, "#eaf6ff"),
    "--route-color-middle": safeColor(root.dataset.transitionColorMiddle, "#f9fbff"),
    "--route-color-end": safeColor(root.dataset.transitionColorEnd, "#fceef6"),
    "--dialog-color-start": safeColor(root.dataset.dialogColorStart, "#ffffff"),
    "--dialog-color-end": safeColor(root.dataset.dialogColorEnd, "#fff1f7"),
    "--dialog-accent": safeColor(root.dataset.dialogAccent, "#7eaed0"),
  };
  Object.entries(colors).forEach(([name, value]) => root.style.setProperty(name, value));
  const safeNumber = (value, fallback, minimum, maximum) => {
    const parsed = Number.parseInt(value, 10);
    return Math.max(minimum, Math.min(maximum, Number.isFinite(parsed) ? parsed : fallback));
  };
  root.style.setProperty("--dialog-radius", `${safeNumber(root.dataset.dialogRadius, 30, 14, 42)}px`);
  root.style.setProperty("--dialog-width", `${safeNumber(root.dataset.dialogWidth, 510, 360, 720)}px`);
  root.style.setProperty("--dialog-backdrop-blur", `${safeNumber(root.dataset.dialogBackdropBlur, 6, 0, 30)}px`);
  try {
    const singleNavigationRaw = sessionStorage.getItem(singleNavigationKey);
    if (singleNavigationRaw) {
      sessionStorage.removeItem(singleNavigationKey);
      sessionStorage.removeItem(key);
      const singleNavigationState = JSON.parse(singleNavigationRaw);
      if (
        singleNavigationState
        && Date.now() - Number(singleNavigationState.startedAt || 0) <= 15000
      ) {
        root.classList.add("is-single-navigation");
        return;
      }
    }
    const raw = sessionStorage.getItem(key);
    if (!raw) return;
    sessionStorage.removeItem(key);
    const state = JSON.parse(raw);
    if (!state || Date.now() - Number(state.startedAt || 0) > 15000) return;
    root.classList.add("is-page-entering");
  } catch (_) {
    // Transitions remain optional when session storage is unavailable.
  }
})();
