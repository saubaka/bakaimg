(() => {
  const root = document.documentElement;
  const body = document.body;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const mobileDrawer = document.querySelector("#mobile-drawer");
  const mobileBackdrop = document.querySelector("[data-mobile-backdrop]");
  const adminSidebar = document.querySelector("#admin-sidebar");
  const adminBackdrop = document.querySelector("[data-admin-backdrop]");
  let lastDrawerTrigger = null;
  let mobileDrawerState = "closed";
  let mobileDrawerCloseTimer = 0;

  const motionIsReduced = () => (
    root.dataset.motion === "reduce"
    || (root.dataset.motion === "system" && reduceMotion.matches)
  );

  if (
    (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4)
    || (navigator.deviceMemory && navigator.deviceMemory <= 4)
  ) {
    root.dataset.performance = "low";
  }

  const toastRegion = document.querySelector("[data-toast-region]");
  const dismissToast = (toast) => {
    if (!toast || toast.dataset.toastState === "leaving") return;
    toast.style.setProperty("--toast-height", `${Math.ceil(toast.scrollHeight)}px`);
    toast.getBoundingClientRect();
    toast.dataset.toastState = "leaving";
    toast.classList.remove("is-visible");
    toast.classList.add("is-leaving");
    let removalTimer = 0;
    const removeToast = (event) => {
      if (event && event.target !== toast) return;
      if (event && event.propertyName !== "max-height") return;
      window.clearTimeout(removalTimer);
      toast.removeEventListener("transitionend", removeToast);
      toast.remove();
      if (toastRegion && !toastRegion.children.length) toastRegion.hidden = true;
    };
    toast.addEventListener("transitionend", removeToast);
    removalTimer = window.setTimeout(removeToast, motionIsReduced() ? 30 : 520);
  };
  toastRegion?.querySelectorAll("[data-toast]").forEach((toast, index) => {
    const category = [...toast.classList].find((name) => name.startsWith("toast--")) || "";
    const visibleDuration = ["toast--error", "toast--warning"].includes(category) ? 6400 : 4600;
    toast.classList.add("is-toast-managed");
    toast.dataset.toastState = "entering";
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        if (!toast.isConnected) return;
        toast.classList.add("is-visible");
        toast.dataset.toastState = "visible";
      });
    });
    window.setTimeout(() => dismissToast(toast), visibleDuration + index * 180);
  });

  const focusableWithin = (container) => [
    ...container.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ];

  const openDialog = (dialog) => {
    if (!dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  };

  const closeDialog = (dialog) => {
    if (!dialog) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  };

  const appSystemDialog = document.querySelector("[data-app-system-dialog]");
  let pendingSystemDialog = null;
  const settleSystemDialog = (value) => {
    if (!pendingSystemDialog) return;
    const { resolve, trigger } = pendingSystemDialog;
    pendingSystemDialog = null;
    closeDialog(appSystemDialog);
    resolve(value);
    if (value === false || value === null) window.setTimeout(() => trigger?.focus(), 0);
  };
  const requestSystemDialog = ({ mode = "confirm", title, message, value = "", inputLabel = "请输入内容" }) => {
    if (!appSystemDialog) return Promise.resolve(mode === "prompt" ? null : false);
    if (pendingSystemDialog) settleSystemDialog(pendingSystemDialog.cancelValue);
    const trigger = document.activeElement;
    const inputField = appSystemDialog.querySelector("[data-app-dialog-field]");
    const input = appSystemDialog.querySelector("[data-app-dialog-input]");
    const cancelButtons = appSystemDialog.querySelectorAll("[data-app-dialog-cancel]");
    const confirmButton = appSystemDialog.querySelector("[data-app-dialog-confirm]");
    const isPrompt = mode === "prompt";
    const isAlert = mode === "alert";
    appSystemDialog.dataset.dialogMode = mode;
    appSystemDialog.querySelector("[data-app-dialog-title]").textContent = title || (isPrompt ? "输入内容" : isAlert ? "提示" : "确认操作");
    appSystemDialog.querySelector("[data-app-dialog-message]").textContent = message || "";
    appSystemDialog.querySelector("[data-app-dialog-input-label]").textContent = inputLabel;
    inputField.hidden = !isPrompt;
    input.value = isPrompt ? value : "";
    cancelButtons.forEach((button) => { button.hidden = isAlert && !button.classList.contains("icon-button"); });
    confirmButton.textContent = isAlert ? "知道了" : "确认";
    openDialog(appSystemDialog);
    window.setTimeout(() => (isPrompt ? input : confirmButton).focus(), 0);
    return new Promise((resolve) => {
      pendingSystemDialog = { resolve, mode, cancelValue: isPrompt ? null : false, trigger };
    });
  };
  const themedConfirm = (message, title = "确认操作") => requestSystemDialog({ mode: "confirm", title, message });
  const themedPrompt = (message, value = "", title = "输入内容") => requestSystemDialog({ mode: "prompt", title, message, value });
  const themedAlert = (message, title = "提示") => requestSystemDialog({ mode: "alert", title, message });
  appSystemDialog?.querySelectorAll("[data-app-dialog-cancel]").forEach((button) => button.addEventListener("click", () => settleSystemDialog(pendingSystemDialog?.cancelValue ?? false)));
  appSystemDialog?.querySelector("[data-app-dialog-confirm]")?.addEventListener("click", () => {
    const value = pendingSystemDialog?.mode === "prompt" ? appSystemDialog.querySelector("[data-app-dialog-input]").value.trim() : true;
    settleSystemDialog(value);
  });
  appSystemDialog?.querySelector("[data-app-dialog-input]")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    settleSystemDialog(event.currentTarget.value.trim());
  });
  appSystemDialog?.addEventListener("cancel", (event) => {
    event.preventDefault();
    settleSystemDialog(pendingSystemDialog?.cancelValue ?? false);
  });

  const setSiteInert = (value) => {
    document
      .querySelectorAll(".site-header, #main-content, .site-footer, .mobile-bottom-nav")
      .forEach((item) => {
        item.inert = value;
      });
  };

  const openMobileDrawer = (trigger) => {
    if (!mobileDrawer || !mobileBackdrop || mobileDrawerState === "open") return;
    window.clearTimeout(mobileDrawerCloseTimer);
    mobileDrawerState = "opening";
    lastDrawerTrigger = trigger;
    mobileDrawer.setAttribute("aria-hidden", "false");
    mobileBackdrop.hidden = false;
    body.classList.add("drawer-open");
    document
      .querySelectorAll("[data-mobile-drawer]")
      .forEach((item) => item.setAttribute("aria-expanded", "true"));
    setSiteInert(true);
    window.requestAnimationFrame(() => {
      mobileDrawer.classList.add("is-open");
      mobileBackdrop.classList.add("is-visible");
      mobileDrawerState = "open";
      focusableWithin(mobileDrawer)[0]?.focus();
    });
  };

  const closeMobileDrawer = () => {
    if (!mobileDrawer || mobileDrawerState === "closed") return;
    mobileDrawerState = "closing";
    mobileDrawer.setAttribute("aria-hidden", "true");
    mobileDrawer.classList.remove("is-open");
    mobileBackdrop?.classList.remove("is-visible");
    body.classList.remove("drawer-open");
    document
      .querySelectorAll("[data-mobile-drawer]")
      .forEach((item) => item.setAttribute("aria-expanded", "false"));
    setSiteInert(false);
    mobileDrawerCloseTimer = window.setTimeout(() => {
      if (mobileBackdrop) mobileBackdrop.hidden = true;
      mobileDrawerState = "closed";
      lastDrawerTrigger?.focus();
    }, motionIsReduced() ? 0 : 360);
  };

  document.querySelectorAll("[data-mobile-drawer]").forEach((trigger) => {
    trigger.addEventListener("click", () => openMobileDrawer(trigger));
  });
  document
    .querySelector("[data-close-mobile-drawer]")
    ?.addEventListener("click", closeMobileDrawer);
  mobileBackdrop?.addEventListener("click", closeMobileDrawer);
  document.addEventListener("keydown", (event) => {
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

  window.addEventListener(
    "resize",
    () => {
      if (window.innerWidth > 860 && mobileDrawerState !== "closed") closeMobileDrawer();
    },
    { passive: true },
  );

  const openAdminDrawer = (trigger) => {
    if (!adminSidebar || !adminBackdrop) return;
    lastDrawerTrigger = trigger;
    adminSidebar.classList.add("is-open");
    adminBackdrop.hidden = false;
    window.requestAnimationFrame(() => adminBackdrop.classList.add("is-visible"));
    trigger.setAttribute("aria-expanded", "true");
    body.classList.add("drawer-open");
    adminSidebar.querySelector("a")?.focus();
  };
  const closeAdminDrawer = () => {
    if (!adminSidebar) return;
    adminSidebar.classList.remove("is-open");
    adminBackdrop?.classList.remove("is-visible");
    body.classList.remove("drawer-open");
    document.querySelector("[data-admin-drawer]")?.setAttribute("aria-expanded", "false");
    window.setTimeout(() => { if (adminBackdrop) adminBackdrop.hidden = true; }, motionIsReduced() ? 0 : 180);
    lastDrawerTrigger?.focus();
  };
  document.querySelector("[data-admin-drawer]")?.addEventListener("click", (event) => openAdminDrawer(event.currentTarget));
  adminBackdrop?.addEventListener("click", closeAdminDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Tab" && adminSidebar?.classList.contains("is-open")) {
      const items = focusableWithin(adminSidebar).filter((item) => item.offsetParent !== null);
      const first = items[0];
      const last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    if (event.key === "Escape" && adminSidebar?.classList.contains("is-open")) closeAdminDrawer();
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 860 && adminSidebar?.classList.contains("is-open")) closeAdminDrawer();
  }, { passive: true });

  document.querySelectorAll(".button:not(:disabled), .card--interactive").forEach((element) => {
    element.addEventListener("pointerdown", () => element.classList.add("is-pressed"));
    ["pointerup", "pointercancel", "pointerleave"].forEach((name) => {
      element.addEventListener(name, () => element.classList.remove("is-pressed"));
    });
  });

  const uploadForm = document.querySelector("[data-upload-form]");
  if (uploadForm && "XMLHttpRequest" in window && "FormData" in window) {
    const fileInput = uploadForm.querySelector("[data-file-input]");
    const uploadStage = uploadForm.querySelector("[data-upload-stage]");
    const uploadEmpty = uploadForm.querySelector("[data-upload-empty]");
    const uploadPreview = uploadForm.querySelector("[data-upload-preview]");
    const previewImage = uploadForm.querySelector("[data-upload-preview-image]");
    const previewBlur = uploadForm.querySelector("[data-upload-preview-blur]");
    const fileLabel = uploadForm.querySelector("[data-file-label]");
    const fileDetail = uploadForm.querySelector("[data-upload-file-detail]");
    const uploadActions = uploadForm.querySelector("[data-upload-actions]");
    const submitButton = uploadForm.querySelector("[data-upload-submit]");
    const progressPanel = uploadForm.querySelector("[data-upload-progress]");
    const progressTrack = progressPanel?.querySelector('[role="progressbar"]');
    const progressFill = progressPanel?.querySelector("[data-upload-progress-fill]");
    const progressStatus = progressPanel?.querySelector("[data-upload-status]");
    const progressPercent = progressPanel?.querySelector("[data-upload-percent]");
    const progressDetail = progressPanel?.querySelector("[data-upload-detail]");
    const originalSubmitLabel = submitButton?.value || submitButton?.textContent || "上传图片";
    let previewUrl = "";
    let dragDepth = 0;

    const releasePreviewUrl = () => {
      if (!previewUrl) return;
      URL.revokeObjectURL(previewUrl);
      previewUrl = "";
    };
    const hideProgress = () => {
      if (!progressPanel || progressPanel.hidden) return;
      progressPanel.classList.add("is-exiting");
      window.setTimeout(() => {
        progressPanel.hidden = true;
        progressPanel.classList.remove("is-visible", "is-exiting", "is-error", "is-complete", "is-processing", "is-uploading");
      }, motionIsReduced() ? 0 : 240);
    };
    const updateFilePreview = () => {
      const files = [...(fileInput?.files || [])];
      const count = files.length;
      releasePreviewUrl();
      uploadStage?.classList.toggle("has-files", count > 0);
      uploadStage?.classList.toggle("is-single", count === 1);
      uploadStage?.classList.toggle("is-multiple", count > 1);
      if (uploadEmpty) uploadEmpty.hidden = count > 0;
      if (uploadPreview) uploadPreview.hidden = count === 0;
      if (uploadActions) uploadActions.hidden = count === 0;
      if (!count) {
        if (previewImage) previewImage.removeAttribute("src");
        if (previewBlur) previewBlur.removeAttribute("src");
        if (fileLabel) fileLabel.textContent = "上传图片";
        if (fileDetail) fileDetail.textContent = "";
        return;
      }
      previewUrl = URL.createObjectURL(files[0]);
      if (previewImage) previewImage.src = previewUrl;
      if (previewBlur) previewBlur.src = previewUrl;
      if (fileLabel) fileLabel.textContent = count === 1 ? files[0].name : `已选择 ${count} 张图片`;
      if (fileDetail) fileDetail.textContent = count === 1 ? "点击图片可以重新选择" : `${files[0].name} 等 ${count} 张`;
      hideProgress();
    };
    fileInput?.addEventListener("change", updateFilePreview);

    const dragHasFiles = (event) => [...(event.dataTransfer?.types || [])].includes("Files");
    uploadStage?.addEventListener("dragenter", (event) => {
      if (!dragHasFiles(event)) return;
      event.preventDefault();
      dragDepth += 1;
      uploadStage.classList.add("is-dragging");
    });
    uploadStage?.addEventListener("dragover", (event) => {
      if (!dragHasFiles(event)) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
      uploadStage.classList.add("is-dragging");
    });
    uploadStage?.addEventListener("dragleave", (event) => {
      if (!dragHasFiles(event)) return;
      dragDepth = Math.max(0, dragDepth - 1);
      if (!dragDepth) uploadStage.classList.remove("is-dragging");
    });
    uploadStage?.addEventListener("drop", (event) => {
      if (!dragHasFiles(event)) return;
      event.preventDefault();
      dragDepth = 0;
      uploadStage.classList.remove("is-dragging");
      const droppedFiles = [...(event.dataTransfer?.files || [])].filter((file) => file.type.startsWith("image/"));
      if (!droppedFiles.length || !fileInput) return;
      try {
        const transfer = new DataTransfer();
        droppedFiles.forEach((file) => transfer.items.add(file));
        fileInput.files = transfer.files;
      } catch (_) {
        fileInput.files = event.dataTransfer.files;
      }
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    });

    const visibility = uploadForm.querySelector("[data-upload-visibility]");
    const visibilityNative = visibility?.querySelector("[data-upload-visibility-native]");
    const visibilityTrigger = visibility?.querySelector("[data-upload-visibility-trigger]");
    const visibilityMenu = visibility?.querySelector("[data-upload-visibility-menu]");
    const visibilityLabel = visibility?.querySelector("[data-upload-visibility-label]");
    const visibilityOptions = [...(visibility?.querySelectorAll("[data-upload-visibility-option]") || [])];
    const setVisibilityOpen = (open, focusOption = false) => {
      visibility?.classList.toggle("is-open", open);
      visibilityTrigger?.setAttribute("aria-expanded", String(open));
      if (visibilityMenu) visibilityMenu.hidden = !open;
      if (open && focusOption) {
        (visibilityOptions.find((option) => option.getAttribute("aria-checked") === "true") || visibilityOptions[0])?.focus();
      }
    };
    const chooseVisibility = (option) => {
      if (!visibilityNative || !option) return;
      visibilityNative.value = option.dataset.uploadVisibilityOption || "private";
      visibilityNative.dispatchEvent(new Event("change", { bubbles: true }));
      if (visibilityLabel) visibilityLabel.textContent = option.querySelector("span")?.textContent || option.textContent.trim();
      visibilityOptions.forEach((item) => item.setAttribute("aria-checked", String(item === option)));
      setVisibilityOpen(false);
      visibilityTrigger?.focus();
    };
    visibilityTrigger?.addEventListener("click", () => setVisibilityOpen(!visibility?.classList.contains("is-open"), true));
    visibilityOptions.forEach((option) => option.addEventListener("click", () => chooseVisibility(option)));
    visibility?.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setVisibilityOpen(false);
        visibilityTrigger?.focus();
        return;
      }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      if (!visibility?.classList.contains("is-open")) setVisibilityOpen(true);
      const currentIndex = Math.max(0, visibilityOptions.indexOf(document.activeElement));
      const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? visibilityOptions.length - 1 : event.key === "ArrowDown" ? (currentIndex + 1) % visibilityOptions.length : (currentIndex - 1 + visibilityOptions.length) % visibilityOptions.length;
      visibilityOptions[nextIndex]?.focus();
    });
    document.addEventListener("pointerdown", (event) => {
      if (visibility && !visibility.contains(event.target)) setVisibilityOpen(false);
    });

    const setUploadProgress = (value) => {
      const progress = Math.max(0, Math.min(100, Math.round(value)));
      progressFill?.style.setProperty("--upload-progress", `${progress}%`);
      progressTrack?.setAttribute("aria-valuenow", String(progress));
      if (progressPercent) progressPercent.textContent = `${progress}%`;
    };
    const setUploadMessage = (status, detail) => {
      if (progressStatus) progressStatus.textContent = status;
      if (progressDetail) progressDetail.textContent = detail;
    };
    const setUploadLocked = (locked) => {
      uploadForm.classList.toggle("is-uploading", locked);
      uploadStage?.classList.toggle("is-uploading", locked);
      [...uploadForm.elements].forEach((control) => { control.disabled = locked; });
      if (submitButton) {
        if ("value" in submitButton) submitButton.value = locked ? "正在上传…" : originalSubmitLabel;
        else submitButton.textContent = locked ? "正在上传…" : originalSubmitLabel;
      }
    };
    const showUploadError = (message) => {
      progressPanel.hidden = false;
      window.requestAnimationFrame(() => progressPanel.classList.add("is-visible"));
      progressPanel.classList.remove("is-uploading", "is-processing", "is-complete");
      progressPanel.classList.add("is-error");
      setUploadProgress(0);
      setUploadMessage("这次没有上传成功", message || "请稍后再试一次。");
      setUploadLocked(false);
      submitButton?.focus();
    };
    uploadForm.addEventListener("submit", (event) => {
      if (uploadForm.dataset.uploadSubmitting === "true") return;
      event.preventDefault();
      if (!uploadForm.reportValidity()) return;
      const count = fileInput?.files?.length || 0;
      if (!count) {
        showUploadError("请先选择至少一张图片。");
        fileInput?.focus();
        return;
      }
      uploadForm.dataset.uploadSubmitting = "true";
      progressPanel.hidden = false;
      progressPanel.classList.remove("is-error", "is-complete", "is-exiting");
      progressPanel.classList.add("is-uploading");
      window.requestAnimationFrame(() => progressPanel.classList.add("is-visible"));
      setUploadProgress(0);
      setUploadMessage("正在上传图片", `${count} 张图片正在保存，请不要关闭页面。`);
      const formData = new FormData(uploadForm);
      setUploadLocked(true);
      const request = new XMLHttpRequest();
      request.open((uploadForm.method || "POST").toUpperCase(), uploadForm.action || window.location.href);
      request.responseType = "json";
      request.setRequestHeader("X-Requested-With", "XMLHttpRequest");
      request.upload.addEventListener("progress", (progressEvent) => {
        if (!progressEvent.lengthComputable) return;
        setUploadProgress((progressEvent.loaded / progressEvent.total) * 100);
        if (progressEvent.loaded >= progressEvent.total) {
          progressPanel.classList.add("is-processing");
          setUploadMessage("正在整理图片", "上传完成，正在把画面安稳地放好。");
        }
      });
      request.addEventListener("load", () => {
        const payload = request.response || {};
        if (request.status < 200 || request.status >= 300 || !payload.ok) {
          uploadForm.dataset.uploadSubmitting = "false";
          showUploadError(payload.message || "请检查图片后再试一次。");
          return;
        }
        progressPanel.classList.remove("is-uploading", "is-processing");
        progressPanel.classList.add("is-complete");
        setUploadProgress(100);
        setUploadMessage("图片已经放好", "正在带你去图库。");
        const target = new URL(payload.redirect || "/images/", window.location.href);
        window.setTimeout(() => {
          progressPanel.classList.add("is-exiting");
          const delay = beginPageLeave(target);
          window.setTimeout(() => window.location.assign(target.href), Math.max(delay, motionIsReduced() ? 0 : 260));
        }, motionIsReduced() ? 0 : 680);
      });
      request.addEventListener("error", () => {
        uploadForm.dataset.uploadSubmitting = "false";
        showUploadError("网络似乎打了个盹，请重试。");
      });
      request.addEventListener("abort", () => {
        uploadForm.dataset.uploadSubmitting = "false";
        showUploadError("上传已取消，可以重新选择图片。");
      });
      request.send(formData);
    });
    window.addEventListener("pagehide", releasePreviewUrl, { once: true });
  }

  document.querySelectorAll("[data-copy-button]").forEach((button) => {
    button.addEventListener("click", async () => {
      const input = button.closest(".copy-field")?.querySelector("[data-copy-source]");
      if (!input) return;
      try {
        await navigator.clipboard.writeText(input.value);
        button.textContent = "已复制";
        window.setTimeout(() => {
          button.textContent = "复制";
        }, 1400);
      } catch (_) {
        input.select();
      }
    });
  });

  const bindConfirmForms = (scope = document) => {
    scope.querySelectorAll("form[data-confirm]").forEach((form) => {
      if (form.dataset.confirmBound === "true") return;
      form.dataset.confirmBound = "true";
      form.addEventListener("submit", (event) => {
        if (form.dataset.confirmApproved === "true") return;
        event.preventDefault();
        const submitter = event.submitter;
        themedConfirm(form.dataset.confirm || "确定继续吗？").then((confirmed) => {
          if (!confirmed) return;
          form.dataset.confirmApproved = "true";
          if (submitter?.isConnected) form.requestSubmit(submitter);
          else form.requestSubmit();
        });
      });
    });
  };
  bindConfirmForms();

  document.querySelectorAll("[data-discover-menu]").forEach((menu) => {
    const trigger = menu.querySelector("[data-discover-menu-trigger]");
    const panel = menu.querySelector("[data-discover-menu-panel]");
    const value = menu.querySelector("[data-discover-menu-value]");
    const label = menu.querySelector("[data-discover-menu-label]");
    const options = [...menu.querySelectorAll("[data-discover-menu-option]")];
    if (!trigger || !panel || !value || !label) return;
    const setOpen = (open, focusOption = false) => {
      menu.classList.toggle("is-open", open);
      trigger.setAttribute("aria-expanded", String(open));
      panel.hidden = !open;
      if (open && focusOption) {
        (options.find((option) => option.getAttribute("aria-checked") === "true") || options[0])?.focus();
      }
    };
    const choose = (option) => {
      value.value = option.dataset.discoverMenuOption;
      label.textContent = option.querySelector("span")?.textContent || option.textContent.trim();
      options.forEach((item) => item.setAttribute("aria-checked", String(item === option)));
      setOpen(false);
      trigger.focus();
    };
    trigger.addEventListener("click", () => setOpen(!menu.classList.contains("is-open"), true));
    options.forEach((option) => option.addEventListener("click", () => choose(option)));
    menu.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        trigger.focus();
        return;
      }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      if (!menu.classList.contains("is-open")) setOpen(true);
      const currentIndex = Math.max(0, options.indexOf(document.activeElement));
      const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 : event.key === "ArrowDown" ? (currentIndex + 1) % options.length : (currentIndex - 1 + options.length) % options.length;
      options[nextIndex]?.focus();
    });
    document.addEventListener("pointerdown", (event) => {
      if (!menu.contains(event.target)) setOpen(false);
    });
  });

  const scheduleMotionReady = (item) => {
    if (!item.classList.contains("card")) return;
    const delay = Number.parseFloat(item.style.getPropertyValue("--card-reveal-delay")) || 0;
    window.setTimeout(() => item.classList.add("is-motion-ready"), motionIsReduced() ? 0 : 760 + delay);
  };
  const revealObserver = !motionIsReduced() && "IntersectionObserver" in window
    ? new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-revealed");
          scheduleMotionReady(entry.target);
          revealObserver.unobserve(entry.target);
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -3%" },
    )
    : null;
  const prepareCardMotion = (scope = document) => {
    const joinsStableArrival = (
      root.classList.contains("is-page-entering")
      || root.classList.contains("is-single-navigation")
    );
    const cards = [...scope.querySelectorAll(".card")];
    cards.forEach((card, index) => {
      card.setAttribute("data-card-motion", "");
      if (!card.hasAttribute("data-reveal")) card.setAttribute("data-reveal", "");
      card.style.setProperty("--card-reveal-delay", `${Math.min(index % 5, 4) * 45}ms`);
    });
    [...scope.querySelectorAll("[data-reveal]")].forEach((item) => {
      if (item.classList.contains("is-revealed")) return;
      if (joinsStableArrival) {
        item.classList.add("is-revealed");
        scheduleMotionReady(item);
      } else if (revealObserver) revealObserver.observe(item);
      else {
        item.classList.add("is-revealed");
        scheduleMotionReady(item);
      }
    });
  };
  prepareCardMotion();

  const libraryTabs = document.querySelector("[data-library-tabs]");
  const libraryResults = document.querySelector("[data-library-results]");
  const libraryGrid = document.querySelector("[data-library-grid]");
  if (libraryTabs && libraryResults && libraryGrid) {
    const indicator = libraryTabs.querySelector("[data-library-tab-indicator]");
    const filters = [...libraryTabs.querySelectorAll("[data-library-filter]")];
    const loader = libraryResults.querySelector("[data-library-filter-loader]");
    const loaderText = loader?.querySelector("small");
    const moreShell = libraryResults.querySelector("[data-library-more-shell]");
    const moreButton = libraryResults.querySelector("[data-library-more]");
    const moreLabel = libraryResults.querySelector("[data-library-more-label]");
    const statNodes = new Map([...document.querySelectorAll("[data-library-stat]")].map((node) => [node.dataset.libraryStat, node]));
    let activeRequest = null;
    let loading = false;
    const formatLibraryBytes = (value) => {
      let amount = Math.max(0, Number(value) || 0);
      const units = ["B", "KiB", "MiB", "GiB", "TiB"];
      let unit = 0;
      while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; unit += 1; }
      const digits = unit === 0 || amount >= 10 ? 0 : 1;
      return `${amount.toFixed(digits)} ${units[unit]}`;
    };
    const updateStats = (stats) => {
      if (!stats) return;
      ["total", "active", "trashed"].forEach((key) => {
        if (statNodes.has(key) && Number.isFinite(Number(stats[key]))) statNodes.get(key).textContent = String(stats[key]);
      });
      if (statNodes.has("bytes")) statNodes.get("bytes").textContent = formatLibraryBytes(stats.bytes);
    };
    const moveIndicator = (filter) => {
      if (!indicator || !filter) return;
      indicator.style.width = `${filter.offsetWidth}px`;
      indicator.style.transform = `translate3d(${filter.offsetLeft}px,0,0)`;
    };
    const setCurrentFilter = (filter) => {
      filters.forEach((item) => {
        const current = item === filter;
        item.classList.toggle("is-current", current);
        if (current) item.setAttribute("aria-current", "page");
        else item.removeAttribute("aria-current");
      });
      moveIndicator(filter);
    };
    const showLoader = (message = "正在读取图片") => {
      if (!loader) return;
      if (loaderText) loaderText.textContent = message;
      loader.hidden = false;
      libraryResults.setAttribute("aria-busy", "true");
      window.requestAnimationFrame(() => loader.classList.add("is-visible"));
    };
    const hideLoader = () => {
      libraryResults.setAttribute("aria-busy", "false");
      loader?.classList.remove("is-visible");
      window.setTimeout(() => { if (loader) loader.hidden = true; }, motionIsReduced() ? 0 : 220);
    };
    const updateMore = (payload, status) => {
      if (!moreShell || !moreButton) return;
      moreShell.hidden = !payload.has_more;
      if (!payload.has_more) return;
      const url = new URL(moreButton.href, window.location.href);
      url.searchParams.set("status", status);
      url.searchParams.set("page", String(payload.next_page));
      moreButton.href = url.href;
    };
    const fetchLibrary = async (url, { append = false, status, fallbackFilter = null } = {}) => {
      if (loading) return;
      loading = true;
      activeRequest = new AbortController();
      let failed = false;
      const loadingStartedAt = window.performance.now();
      if (append) {
        moreButton?.classList.add("is-loading");
        if (moreLabel) moreLabel.textContent = "正在加载";
      } else {
        showLoader();
        libraryGrid.classList.add("is-filter-loading");
      }
      try {
        const response = await fetch(url, {
          headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
          signal: activeRequest.signal,
          credentials: "same-origin",
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.message || "读取失败");
        const minimumLoadingTime = motionIsReduced() ? 0 : append ? 320 : 380;
        const remainingLoadingTime = minimumLoadingTime - (window.performance.now() - loadingStartedAt);
        if (remainingLoadingTime > 0) {
          await new Promise((resolve) => window.setTimeout(resolve, remainingLoadingTime));
        }
        const fragment = document.createRange().createContextualFragment(payload.html || "");
        if (append) libraryGrid.append(fragment);
        else libraryGrid.replaceChildren(fragment);
        prepareCardMotion(libraryGrid);
        bindConfirmForms(libraryGrid);
        updateMore(payload, payload.status || status);
        updateStats(payload.stats);
        if (!append) {
          const nextUrl = new URL(url, window.location.href);
          nextUrl.searchParams.delete("page");
          window.history.replaceState({}, "", nextUrl);
        }
      } catch (error) {
        if (error.name !== "AbortError") {
          failed = true;
          if (!append && fallbackFilter) setCurrentFilter(fallbackFilter);
          showLoader("暂时没能读取，请再试一次");
          window.setTimeout(hideLoader, 1600);
        }
      } finally {
        loading = false;
        libraryGrid.classList.remove("is-filter-loading");
        moreButton?.classList.remove("is-loading");
        if (moreLabel) moreLabel.textContent = "继续加载";
        if (!failed) hideLoader();
      }
    };
    filters.forEach((filter) => filter.addEventListener("click", (event) => {
      event.preventDefault();
      if (filter.classList.contains("is-current") || loading) return;
      const fallbackFilter = libraryTabs.querySelector(".is-current");
      setCurrentFilter(filter);
      const delay = motionIsReduced() ? 0 : 230;
      window.setTimeout(() => fetchLibrary(filter.href, { status: filter.dataset.libraryFilter, fallbackFilter }), delay);
    }));
    moreButton?.addEventListener("click", (event) => {
      event.preventDefault();
      if (!loading) fetchLibrary(moreButton.href, { append: true, status: libraryTabs.querySelector(".is-current")?.dataset.libraryFilter || "active" });
    });
    libraryTabs.classList.add("is-enhanced");
    window.requestAnimationFrame(() => moveIndicator(libraryTabs.querySelector(".is-current")));
    window.addEventListener("resize", () => moveIndicator(libraryTabs.querySelector(".is-current")), { passive: true });
  }

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
      window.requestAnimationFrame(updateCapsuleNavigation);
    };
    const resetCapsuleNavigation = () => {
      previousScrollY = Math.max(0, window.scrollY);
      setCapsuleVisible(true);
      requestCapsuleUpdate();
    };
    const playCapsuleArrival = () => {
      window.clearTimeout(arrivalTimer);
      capsuleNavigation.classList.remove("is-nav-arriving");
      if (capsuleViewport.matches && !motionIsReduced()) {
        window.requestAnimationFrame(() => capsuleNavigation.classList.add("is-nav-arriving"));
      }
      arrivalTimer = window.setTimeout(
        () => capsuleNavigation.classList.remove("is-nav-arriving"),
        680,
      );
    };
    setCapsuleVisible(true);
    if (!root.classList.contains("is-single-navigation")) playCapsuleArrival();
    window.addEventListener("scroll", requestCapsuleUpdate, { passive: true });
    window.addEventListener("resize", resetCapsuleNavigation, { passive: true });
    capsuleViewport.addEventListener?.("change", resetCapsuleNavigation);
    window.addEventListener("pageshow", (event) => {
      if (event.persisted) resetCapsuleNavigation();
    });
  }

  const navigationLinks = document.querySelector(".site-nav__links");
  const currentNavigationLink = navigationLinks?.querySelector(".is-current");
  if (navigationLinks && currentNavigationLink) {
    const indicator = document.createElement("span");
    indicator.className = "nav-indicator";
    indicator.setAttribute("aria-hidden", "true");
    navigationLinks.prepend(indicator);
    const moveIndicator = (link) => {
      const linkRect = link.getBoundingClientRect();
      indicator.style.width = `${linkRect.width}px`;
      indicator.style.height = `${linkRect.height}px`;
      indicator.style.transform = `translate3d(${link.offsetLeft}px,${link.offsetTop}px,0)`;
    };
    window.requestAnimationFrame(() => moveIndicator(currentNavigationLink));
    navigationLinks.querySelectorAll("a").forEach((link) => {
      link.addEventListener("pointerenter", () => moveIndicator(link), { passive: true });
    });
    navigationLinks.addEventListener(
      "pointerleave",
      () => moveIndicator(currentNavigationLink),
      { passive: true },
    );
    window.addEventListener("resize", () => moveIndicator(currentNavigationLink), {
      passive: true,
    });
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
        window.clearTimeout(previous.timer);
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
        window.clearTimeout(adminAccordionTransitions.get(panel)?.timer);
        adminAccordionTransitions.delete(panel);
      };
      panel.addEventListener("transitionend", finish);
      const timer = window.setTimeout(() => finish(), duration + 90);
      adminAccordionTransitions.set(panel, { token, timer, finish });
      window.requestAnimationFrame(() => {
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
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => { adminNavigation.dataset.accordionReady = "true"; }));
    adminMenuGroups.forEach((group) => {
      group.querySelector(":scope > [data-admin-menu-toggle]")?.addEventListener("click", () => {
        setAdminMenuGroup(group.classList.contains("is-open") ? null : group);
      });
    });
  }

  const routeTransitionKey = "cloudnest-route-transition";
  const singleNavigationKey = "cloudnest-single-navigation";
  let singleNavigationPending = false;
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
    window.setTimeout(() => root.classList.remove("is-page-entering"), Math.max(1100, Math.round(configuredTransitionDuration() * 1.6)));
  }
  if (root.classList.contains("is-single-navigation")) {
    window.requestAnimationFrame(() => root.classList.remove("is-single-navigation"));
  }
  window.addEventListener("pageshow", () => root.classList.remove("is-page-leaving"));

  document.addEventListener("click", (event) => {
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
      if (singleNavigationPending) return;
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
    window.setTimeout(() => window.location.assign(target.href), delay);
  });

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (event.defaultPrevented || form.dataset.transitionSubmitting === "true" || !form.checkValidity() || form.target === "_blank") return;
    const target = new URL(form.action || window.location.href, window.location.href);
    if (target.origin !== window.location.origin) return;
    const delay = beginPageLeave(target);
    if (!delay) return;
    event.preventDefault();
    const submitter = event.submitter;
    window.setTimeout(() => {
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
    trigger?.addEventListener("click", (event) => {
      event.stopPropagation();
      setOpen(!menu.classList.contains("is-open"));
    });
    menu.addEventListener("mouseenter", () => setOpen(true));
    document.addEventListener("pointermove", (event) => {
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
      if (!insideTrigger && !insidePanel && !insideDownwardBridge) setOpen(false);
    });
    menu.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        setOpen(false);
        trigger?.blur();
      }
    });
    menu.addEventListener("focusout", () =>
      window.setTimeout(() => {
        if (!menu.matches(":focus-within")) setOpen(false);
      }, 0),
    );
    document.addEventListener("click", (event) => {
      if (!menu.contains(event.target)) setOpen(false);
    });
  });

  document.querySelectorAll("[data-gateway-connection-editor]").forEach((editor) => {
    const panel = editor.querySelector("[data-gateway-editor-panel]");
    const inner = panel?.querySelector(".gateway-connection-editor__inner");
    const toggles = [...editor.querySelectorAll("[data-gateway-editor-toggle]")];
    const closeButtons = [...editor.querySelectorAll("[data-gateway-editor-close]")];
    if (!panel || !inner) return;
    const setEditorOpen = (open) => {
      editor.dataset.editorReady = "true";
      panel.classList.toggle("is-open", open);
      panel.setAttribute("aria-hidden", String(!open));
      toggles.forEach((button) => button.setAttribute("aria-expanded", String(open)));
      panel.style.height = open ? `${inner.scrollHeight}px` : "0px";
      if (open) window.setTimeout(() => panel.querySelector("input")?.focus(), 280);
    };
    toggles.forEach((button) => {
      button.addEventListener("click", () => {
        setEditorOpen(!panel.classList.contains("is-open"));
      });
    });
    closeButtons.forEach((button) => {
      button.addEventListener("click", () => setEditorOpen(false));
    });
    window.addEventListener("resize", () => {
      if (panel.classList.contains("is-open")) panel.style.height = `${inner.scrollHeight}px`;
    });
    setEditorOpen(editor.dataset.editorStartOpen === "true");
  });

  document.querySelectorAll("[data-gateway-auto-continue]").forEach((panel) => {
    const continueUrl = panel.dataset.continueUrl;
    const delay = Number.parseInt(panel.dataset.continueDelay || "1100", 10);
    if (!continueUrl) return;
    window.setTimeout(() => window.location.assign(continueUrl), Math.max(250, delay));
  });

  const previewTimers = new WeakMap();
  const replayPreview = (target, className = "is-preview-updating") => {
    if (!target || motionIsReduced()) return;
    window.clearTimeout(previewTimers.get(target));
    target.classList.remove(className);
    void target.offsetWidth;
    window.requestAnimationFrame(() => target.classList.add(className));
    previewTimers.set(target, window.setTimeout(() => target.classList.remove(className), 620));
  };
  document.querySelector("[data-hint-settings]")?.querySelector('input[name="admin_menu_subtitles_visible"]')?.addEventListener("change", (event) => {
    document.querySelector(".admin-shell")?.classList.toggle("admin-menu--compact", !event.target.checked);
    replayPreview(event.target.closest(".hint-control-card"), "is-choice-switching");
  });
  const transitionSettings = document.querySelector("[data-transition-settings]");
  const transitionDurationInput = document.querySelector("[data-transition-duration-input]");
  const transitionDurationRange = document.querySelector("[data-transition-duration-range]");
  const transitionDurationOutput = document.querySelector("[data-transition-duration-output]");
  const replayTransitionChoice = (input) => {
    replayPreview(input?.closest(".transition-choice"), "is-choice-switching");
    replayPreview(input?.closest(".transition-choice")?.querySelector(".transition-choice__demo"), "is-preview-playing");
  };
  const syncTransitionDuration = (rawValue) => {
    const duration = Math.max(300, Math.min(2400, Number.parseInt(rawValue, 10) || 720));
    if (transitionDurationInput) transitionDurationInput.value = String(duration);
    if (transitionDurationRange) transitionDurationRange.value = String(duration);
    if (transitionDurationOutput) transitionDurationOutput.textContent = `${duration} ms`;
    root.dataset.transitionDuration = String(duration);
    root.style.setProperty("--route-duration", `${duration}ms`);
    root.style.setProperty("--theme-preview-duration", `${Math.min(duration, 1500)}ms`);
    replayTransitionChoice(transitionSettings?.querySelector('input[name="transition_style"]:checked'));
  };
  transitionDurationInput?.addEventListener("input", (event) => syncTransitionDuration(event.target.value));
  transitionDurationRange?.addEventListener("input", (event) => syncTransitionDuration(event.target.value));
  transitionSettings?.querySelectorAll('input[name="transition_style"]').forEach((input) => input.addEventListener("change", () => {
    if (!input.checked) return;
    root.dataset.pageTransition = input.value;
    replayTransitionChoice(input);
    replayPreview(transitionSettings);
  }));
  const appearanceColorVariables = {
    transition_color_start: "--route-color-start",
    transition_color_middle: "--route-color-middle",
    transition_color_end: "--route-color-end",
    dialog_color_start: "--dialog-color-start",
    dialog_color_end: "--dialog-color-end",
    dialog_accent: "--dialog-accent",
  };
  document.querySelectorAll('.appearance-color-field input[type="color"]').forEach((input) => input.addEventListener("input", () => {
    const variable = appearanceColorVariables[input.name];
    if (variable) root.style.setProperty(variable, input.value);
    const output = input.closest(".appearance-color-field")?.querySelector("[data-color-value]");
    if (output) output.textContent = input.value.toUpperCase();
    replayPreview(input.closest(".appearance-color-field"), "is-choice-switching");
  }));
  document.querySelectorAll('input[name="dialog_style"]').forEach((input) => input.addEventListener("change", () => {
    if (!input.checked) return;
    root.dataset.dialogStyle = input.value;
    replayPreview(input.closest(".dialog-style-choice"), "is-choice-switching");
  }));
  const dialogMetrics = {
    radius: { minimum: 14, maximum: 42, fallback: 30, variable: "--dialog-radius" },
    width: { minimum: 360, maximum: 720, fallback: 510, variable: "--dialog-width" },
    blur: { minimum: 0, maximum: 30, fallback: 6, variable: "--dialog-backdrop-blur" },
  };
  const syncDialogMetric = (name, rawValue) => {
    const config = dialogMetrics[name];
    if (!config) return;
    const parsed = Number.parseInt(rawValue, 10);
    const value = Math.max(config.minimum, Math.min(config.maximum, Number.isFinite(parsed) ? parsed : config.fallback));
    document.querySelectorAll(`[data-dialog-range="${name}"], [data-dialog-value="${name}"]`).forEach((control) => { control.value = String(value); });
    const output = document.querySelector(`[data-dialog-output="${name}"]`);
    if (output) output.textContent = `${value} px`;
    root.style.setProperty(config.variable, `${value}px`);
  };
  document.querySelectorAll("[data-dialog-value]").forEach((input) => {
    syncDialogMetric(input.dataset.dialogValue, input.value);
    input.addEventListener("input", () => syncDialogMetric(input.dataset.dialogValue, input.value));
  });
  document.querySelectorAll("[data-dialog-range]").forEach((input) => input.addEventListener("input", () => syncDialogMetric(input.dataset.dialogRange, input.value)));
  document.querySelectorAll('input[name="dialog_shadow"]').forEach((input) => input.addEventListener("change", () => {
    if (input.checked) root.dataset.dialogShadow = input.value;
  }));
  document.querySelectorAll("[data-dialog-preview]").forEach((button) => button.addEventListener("click", () => {
    if (button.dataset.dialogPreview === "prompt") themedPrompt("", "", "输入内容");
    else if (button.dataset.dialogPreview === "alert") themedAlert("操作已完成。", "提示");
    else themedConfirm("是否继续？", "确认操作");
  }));

  document.querySelectorAll("[data-fallback-image]").forEach((image) => {
    const container = image.closest("[data-fallback-media]");
    const fallback = () => {
      image.hidden = true;
      container?.classList.add("is-fallback");
    };
    image.addEventListener("error", fallback, { once: true });
    image.addEventListener("load", () => container?.classList.add("has-image"), { once: true });
    if (image.complete && image.naturalWidth === 0) fallback();
  });

})();
