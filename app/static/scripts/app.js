(() => {
  const root = document.documentElement;
  const motionIsReduced = window.BakaUI.motion.reduced;
  const prepareCardMotion = (scope) => window.BakaUI.motion.prepare(scope);
  const beginPageLeave = (target) => window.BakaUI.navigation.beginPageLeave(target);

  if (
    (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4)
    || (navigator.deviceMemory && navigator.deviceMemory <= 4)
  ) {
    root.dataset.performance = "low";
  }

  const { confirm: themedConfirm, prompt: themedPrompt, alert: themedAlert } = window.BakaUI.dialogs;

  // 页面里的内容可以被局部换页替换：换页前先触发 baka:page-leave 做清理，换页后再重新初始化。
  let pageScope = null;
  const initPage = () => {
  pageScope?.abort();
  pageScope = new AbortController();
  const { signal } = pageScope;
  const whenLeaving = (handler) => {
    window.addEventListener("pagehide", handler, { signal });
    window.addEventListener("baka:page-leave", handler, { signal, once: true });
  };

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
    let uploadRequest = null, uploadVersion = 0, suspended = false, interrupted = false;
    let progressTimer = 0, successTimer = 0, redirectTimer = 0;
    const disabledBeforeUpload = new Map();

    const releasePreviewUrl = () => {
      if (!previewUrl) return;
      URL.revokeObjectURL(previewUrl);
      previewUrl = "";
    };
    const hideProgress = () => {
      window.clearTimeout(progressTimer);
      if (!progressPanel || progressPanel.hidden) return;
      progressPanel.classList.add("is-exiting");
      progressTimer = window.setTimeout(() => {
        progressPanel.hidden = true;
        progressPanel.classList.remove("is-visible", "is-exiting", "is-error", "is-complete", "is-processing", "is-uploading");
      }, motionIsReduced() ? 0 : 240);
    };
    const updateFilePreview = () => {
      const files = [...(fileInput?.files || [])];
      const count = files.length;
      if (uploadForm.dataset.uploadSubmitting === "true") return;
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
      if (uploadForm.dataset.uploadSubmitting === "true") return;
      dragDepth += 1;
      uploadStage.classList.add("is-dragging");
    });
    uploadStage?.addEventListener("dragover", (event) => {
      if (!dragHasFiles(event)) return;
      event.preventDefault();
      if (uploadForm.dataset.uploadSubmitting === "true") {
        if (event.dataTransfer) event.dataTransfer.dropEffect = "none";
        return;
      }
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
      if (uploadForm.dataset.uploadSubmitting === "true") return;
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
      [...uploadForm.elements].forEach((control) => {
        if (locked) { if (!disabledBeforeUpload.has(control)) disabledBeforeUpload.set(control, control.disabled); control.disabled = true; }
        else { control.disabled = disabledBeforeUpload.get(control) || false; }
      });
      if (!locked) disabledBeforeUpload.clear();
      if (submitButton) {
        submitButton.setAttribute("aria-busy", String(locked));
        if ("value" in submitButton) submitButton.value = locked ? "正在上传…" : originalSubmitLabel;
        else submitButton.textContent = locked ? "正在上传…" : originalSubmitLabel;
      }
    };
    const showUploadError = (message) => {
      window.clearTimeout(progressTimer);
      progressPanel.hidden = false;
      window.requestAnimationFrame(() => progressPanel.classList.add("is-visible"));
      progressPanel.classList.remove("is-uploading", "is-processing", "is-complete", "is-exiting");
      progressPanel.classList.add("is-error");
      setUploadProgress(0);
      setUploadMessage("这次没有上传成功", message || "请稍后再试一次。");
      setUploadLocked(false);
      submitButton?.focus();
    };
    uploadForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (uploadForm.dataset.uploadSubmitting === "true") return;
      if (!uploadForm.reportValidity()) return;
      const count = fileInput?.files?.length || 0;
      if (!count) {
        showUploadError("请先选择至少一张图片。");
        fileInput?.focus();
        return;
      }
      uploadForm.dataset.uploadSubmitting = "true";
      window.clearTimeout(progressTimer); window.clearTimeout(successTimer); window.clearTimeout(redirectTimer);
      suspended = false;
      const version = ++uploadVersion;
      progressPanel.hidden = false;
      progressPanel.classList.remove("is-error", "is-complete", "is-exiting");
      progressPanel.classList.add("is-uploading");
      window.requestAnimationFrame(() => progressPanel.classList.add("is-visible"));
      setUploadProgress(0);
      setUploadMessage("正在上传图片…", `${count} 张图片正在保存，请不要关闭页面。`);
      const formData = new FormData(uploadForm);
      setUploadLocked(true);
      const request = uploadRequest = new XMLHttpRequest();
      request.open((uploadForm.method || "POST").toUpperCase(), uploadForm.action || window.location.href);
      request.responseType = "json";
      request.timeout = 120000;
      request.setRequestHeader("X-Requested-With", "XMLHttpRequest");
      request.upload.addEventListener("progress", (progressEvent) => {
        if (version !== uploadVersion || suspended) return;
        if (!progressEvent.lengthComputable) return;
        setUploadProgress((progressEvent.loaded / progressEvent.total) * 100);
        if (progressEvent.loaded >= progressEvent.total) {
          progressPanel.classList.add("is-processing");
          setUploadMessage("正在保存图片…", "图片已传输，正在保存。");
        }
      });
      request.addEventListener("load", () => {
        if (version !== uploadVersion || suspended) return;
        uploadRequest = null;
        const payload = request.response || {};
        if (request.status < 200 || request.status >= 300 || !payload.ok) {
          uploadForm.dataset.uploadSubmitting = "false";
          showUploadError(payload.message || "请检查图片后再试一次。");
          return;
        }
        progressPanel.classList.remove("is-uploading", "is-processing");
        progressPanel.classList.add("is-complete");
        setUploadProgress(100);
        setUploadMessage("图片已保存", "正在打开图库…");
        const target = new URL(payload.redirect || "/images/", window.location.href);
        successTimer = window.setTimeout(() => {
          if (version !== uploadVersion || suspended) return;
          progressPanel.classList.add("is-exiting");
          const shell = window.BakaUI.shell;
          const delay = shell ? 0 : beginPageLeave(target);
          redirectTimer = window.setTimeout(() => {
            if (version !== uploadVersion || suspended) return;
            if (!shell?.visit(target.href)) window.location.assign(target.href);
          }, Math.max(delay, motionIsReduced() ? 0 : 260));
        }, motionIsReduced() ? 0 : 680);
      });
      request.addEventListener("error", () => {
        if (version !== uploadVersion || suspended) return;
        uploadRequest = null;
        uploadForm.dataset.uploadSubmitting = "false";
        showUploadError("连接中断，请重试。");
      });
      request.addEventListener("abort", () => {
        if (version !== uploadVersion || suspended) return;
        uploadRequest = null;
        uploadForm.dataset.uploadSubmitting = "false";
        showUploadError("上传已取消，可以重新选择图片。");
      });
      request.addEventListener("timeout", () => {
        if (version !== uploadVersion || suspended) return;
        uploadRequest = null; uploadForm.dataset.uploadSubmitting = "false";
        showUploadError("等待时间较长，请检查图库后重试。");
      });
      request.send(formData);
    });
    whenLeaving(() => {
      interrupted = uploadForm.dataset.uploadSubmitting === "true";
      suspended = true; uploadVersion++;
      window.clearTimeout(progressTimer); window.clearTimeout(successTimer); window.clearTimeout(redirectTimer);
      uploadRequest?.abort(); uploadRequest = null; releasePreviewUrl();
      uploadForm.dataset.uploadSubmitting = "false"; setUploadLocked(false);
      dragDepth = 0; uploadStage?.classList.remove("is-dragging");
    });
    window.addEventListener("pageshow", event => {
      if (!event.persisted) return;
      suspended = false; updateFilePreview();
      if (interrupted) showUploadError("上传已中断，请先查看图库，未保存的图片可以重新上传。");
      interrupted = false;
    }, { signal });
  }

  document.querySelectorAll("[data-copy-button]").forEach((button) => {
    button.addEventListener("click", async () => {
      const input = button.closest(".copy-field")?.querySelector("[data-copy-source]");
      if (!input) return;
      let copied = false;
      try {
        await navigator.clipboard.writeText(input.value);
        copied = true;
      } catch (_) {
        input.select();
        try { copied = document.execCommand("copy"); } catch (__) { copied = false; }
      }
      button.textContent = copied ? "已复制" : "已选中";
      window.setTimeout(() => {
        button.textContent = "复制";
      }, 1400);
    });
  });

  const bindConfirmForms = (scope = document) => {
    scope.querySelectorAll("form[data-confirm]").forEach((form) => {
      if (form.dataset.confirmBound === "true") return;
      form.dataset.confirmBound = "true";
      form.addEventListener("submit", (event) => {
        if (form.dataset.confirmApproved === "true") return;
        event.preventDefault();
        if (form.dataset.confirmPending === "true") return;
        form.dataset.confirmPending = "true";
        const submitter = event.submitter;
        themedConfirm(form.dataset.confirm || "确定继续吗？", "确认操作", /永久删除|删除相册/.test(form.dataset.confirm)).then((confirmed) => {
          delete form.dataset.confirmPending;
          if (!confirmed) return;
          form.dataset.confirmApproved = "true";
          if (submitter?.isConnected) form.requestSubmit(submitter);
          else form.requestSubmit();
        });
      });
    });
  };
  bindConfirmForms();
  whenLeaving(() => document.querySelectorAll('form[data-confirm]').forEach(form => {
    delete form.dataset.confirmApproved; delete form.dataset.confirmPending;
  }));

  window.BakaUI.controls.prepare();
  window.BakaUI.motion.prepare(document, { initial: true });

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
    const libraryError = libraryResults.querySelector("[data-library-error]");
    const retryButton = libraryResults.querySelector("[data-library-retry]");
    let failedRequest = null;
    const statNodes = new Map([...document.querySelectorAll("[data-library-stat]")].map((node) => [node.dataset.libraryStat, node]));
    let activeRequest = null;
    let loading = false;
    let requestVersion = 0, filterTimer = 0, loaderTimer = 0, errorTimer = 0;
    let committedFilter = libraryTabs.querySelector(".is-current");
    const waits = new Map();
    const wait = duration => new Promise(resolve => {
      const timer = window.setTimeout(() => { waits.delete(timer); resolve(); }, duration);
      waits.set(timer, resolve);
    });
    const cancelWaits = () => {
      waits.forEach((resolve, timer) => { window.clearTimeout(timer); resolve(); }); waits.clear();
    };
    const cancelRequest = () => {
      requestVersion++; activeRequest?.abort(); activeRequest = null;
      window.clearTimeout(filterTimer); filterTimer = 0;
      window.clearTimeout(errorTimer); errorTimer = 0;
      cancelWaits(); loading = false;
    };
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
    // 分段选择的滑块由设计系统的 --i 变量定位：点击的那一刻就滑过去，不等请求。
    const moveIndicator = (filter) => {
      if (!indicator || !filter) return;
      libraryTabs.style.setProperty("--i", String(Math.max(0, filters.indexOf(filter))));
    };
    const setCurrentFilter = (filter) => {
      filters.forEach((item) => {
        const current = item === filter;
        item.classList.toggle("is-current", current);
        item.classList.toggle("is-active", current);
        if (current) item.setAttribute("aria-current", "page");
        else item.removeAttribute("aria-current");
      });
      moveIndicator(filter);
    };
    const showLoader = (message = "正在读取图片…") => {
      if (!loader) return;
      window.clearTimeout(loaderTimer);
      if (loaderText) loaderText.textContent = message;
      loader.hidden = false;
      libraryResults.setAttribute("aria-busy", "true");
      window.requestAnimationFrame(() => { if (!loader.hidden) loader.classList.add("is-visible"); });
    };
    const hideLoader = () => {
      libraryResults.setAttribute("aria-busy", "false");
      loader?.classList.remove("is-visible");
      window.clearTimeout(loaderTimer);
      loaderTimer = window.setTimeout(() => { if (loader) loader.hidden = true; }, motionIsReduced() ? 0 : 220);
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
      const version = ++requestVersion;
      const request = activeRequest = new AbortController();
      if (libraryError) libraryError.hidden = true;
      failedRequest = null;
      const loadingStartedAt = window.performance.now();
      if (append) {
        moreButton?.classList.add("is-loading");
        if (moreLabel) moreLabel.textContent = "正在加载…";
      } else {
        showLoader();
        libraryGrid.classList.add("is-filter-loading");
      }
      try {
        const response = await fetch(url, {
          headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
          signal: request.signal,
          credentials: "same-origin",
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.message || "读取失败");
        if (typeof payload.html !== "string" || !payload.stats
          || !["active", "quarantined", "trashed"].includes(payload.status)
          || ["total", "active", "trashed", "bytes"].some(key => !Number.isFinite(Number(payload.stats[key])))
          || (payload.has_more && (!Number.isInteger(payload.next_page) || payload.next_page < 2))) throw new Error("读取失败");
        const minimumLoadingTime = motionIsReduced() ? 0 : append ? 320 : 380;
        const remainingLoadingTime = minimumLoadingTime - (window.performance.now() - loadingStartedAt);
        if (remainingLoadingTime > 0) {
          await wait(remainingLoadingTime);
        }
        if (version !== requestVersion || request.signal.aborted) return;
        const fragment = document.createRange().createContextualFragment(payload.html || "");
        if (append) libraryGrid.append(fragment);
        else libraryGrid.replaceChildren(fragment);
        prepareCardMotion(libraryGrid);
        bindConfirmForms(libraryGrid);
        updateMore(payload, payload.status || status);
        updateStats(payload.stats);
        if (!append) {
          committedFilter = filters.find(filter => filter.dataset.libraryFilter === payload.status);
          setCurrentFilter(committedFilter);
          const nextUrl = new URL(url, window.location.href);
          nextUrl.searchParams.delete("page");
          window.history.replaceState({}, "", nextUrl);
        }
      } catch (error) {
        if (version !== requestVersion) return;
        if (error.name !== "AbortError") {
          if (!append && fallbackFilter) setCurrentFilter(fallbackFilter);
          failedRequest = { url, append, status, fallbackFilter };
          if (libraryError) libraryError.hidden = false;
        }
      } finally {
        if (version === requestVersion) {
          activeRequest = null; loading = false;
          libraryGrid.classList.remove("is-filter-loading");
          moreButton?.classList.remove("is-loading");
          if (moreLabel) moreLabel.textContent = "继续加载";
          hideLoader();
        }
      }
    };
    retryButton?.addEventListener("click", () => {
      if (!failedRequest || loading) return;
      const pending = failedRequest;
      cancelRequest();
      if (!pending.append) setCurrentFilter(filters.find(filter => filter.dataset.libraryFilter === pending.status));
      fetchLibrary(pending.url, pending);
    });
    filters.forEach((filter) => filter.addEventListener("click", (event) => {
      event.preventDefault();
      if (filter.classList.contains("is-current")) return;
      cancelRequest();
      const fallbackFilter = committedFilter;
      failedRequest = null; if (libraryError) libraryError.hidden = true;
      setCurrentFilter(filter);
      const delay = motionIsReduced() ? 0 : 230;
      filterTimer = window.setTimeout(() => {
        filterTimer = 0;
        fetchLibrary(filter.href, { status: filter.dataset.libraryFilter, fallbackFilter });
      }, delay);
    }));
    moreButton?.addEventListener("click", (event) => {
      event.preventDefault();
      if (!loading && !filterTimer) fetchLibrary(moreButton.href, { append: true, status: libraryTabs.querySelector(".is-current")?.dataset.libraryFilter || "active" });
    });
    libraryTabs.classList.add("is-enhanced");
    window.requestAnimationFrame(() => moveIndicator(libraryTabs.querySelector(".is-current")));
    window.addEventListener("resize", () => moveIndicator(libraryTabs.querySelector(".is-current")), { passive: true, signal });
    whenLeaving(() => {
      cancelRequest(); window.clearTimeout(loaderTimer);
      failedRequest = null; if (libraryError) libraryError.hidden = true;
      if (committedFilter) setCurrentFilter(committedFilter);
      libraryResults.setAttribute("aria-busy", "false");
      libraryGrid.classList.remove("is-filter-loading");
      moreButton?.classList.remove("is-loading");
      if (moreLabel) moreLabel.textContent = "继续加载";
      if (loader) { loader.hidden = true; loader.classList.remove("is-visible"); }
    });
  }

  document.querySelectorAll("[data-gateway-connection-editor]").forEach((editor) => {
    const panel = editor.querySelector("[data-gateway-editor-panel]");
    const inner = panel?.querySelector(".gateway-connection-editor__inner");
    const toggles = [...editor.querySelectorAll("[data-gateway-editor-toggle]")];
    const closeButtons = [...editor.querySelectorAll("[data-gateway-editor-close]")];
    if (!panel || !inner) return;
    let focusTimer = 0;
    const setEditorOpen = (open) => {
      window.clearTimeout(focusTimer);
      editor.dataset.editorReady = "true";
      panel.classList.toggle("is-open", open);
      panel.inert = !open;
      panel.setAttribute("aria-hidden", String(!open));
      toggles.forEach((button) => button.setAttribute("aria-expanded", String(open)));
      panel.style.height = open ? `${inner.scrollHeight}px` : "0px";
      if (open) focusTimer = window.setTimeout(() => { if (panel.classList.contains('is-open')) panel.querySelector("input")?.focus(); }, 280);
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
    window.addEventListener('pagehide', () => window.clearTimeout(focusTimer));
  });

  document.querySelectorAll("[data-gateway-auto-continue]").forEach((panel) => {
    const continueUrl = panel.dataset.continueUrl;
    const delay = Number.parseInt(panel.dataset.continueDelay || "1100", 10);
    if (!continueUrl) return;
    const continueTimer = window.setTimeout(() => window.location.assign(continueUrl), Math.max(250, delay));
    whenLeaving(() => window.clearTimeout(continueTimer));
  });

  const previewTimers = new WeakMap(), previewTasks = new Set(), previewFrames = new Set();
  const replayPreview = (target, className = "is-preview-updating") => {
    if (!target || motionIsReduced()) return;
    window.clearTimeout(previewTimers.get(target));
    previewTasks.delete(previewTimers.get(target));
    target.classList.remove(className);
    void target.offsetWidth;
    const frame = window.requestAnimationFrame(() => { previewFrames.delete(frame); target.classList.add(className); });
    previewFrames.add(frame);
    const timer = window.setTimeout(() => { previewTasks.delete(timer); target.classList.remove(className); }, 620);
    previewTimers.set(target, timer); previewTasks.add(timer);
  };
  window.addEventListener('pagehide', () => {
    previewTasks.forEach(window.clearTimeout); previewTasks.clear();
    previewFrames.forEach(window.cancelAnimationFrame); previewFrames.clear();
    document.querySelectorAll('.is-preview-playing,.is-preview-updating,.is-choice-switching').forEach(node => node.classList.remove('is-preview-playing','is-preview-updating','is-choice-switching'));
  });
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

  };
  initPage();
  window.addEventListener("baka:page-ready", initPage);
  window.BakaUI.navigation.init();
})();
