/**
 * Tagger page: bottom dock + reliable Start/Prefetch with immediate feedback.
 * Vue buttons are not moved (would break handlers); dock uses native actions.
 */
(function () {
  const POLL_MS = 1200;
  const BURST_POLL_MS = 300;
  const BURST_COUNT = 120;

  const PHASE_LABEL = {
    idle: "空闲",
    downloading: "下载模型",
    tagging: "打标中",
    done: "完成",
    error: "失败",
    pending: "处理中",
    cancelling: "中止中",
  };

  const IDLE_DOCK = {
    phase: "idle",
    message: "配置参数后点击启动",
    download: {
      current: 0,
      total: 0,
      filename: "",
      bytes_current: 0,
      bytes_total: 0,
      percent: 0,
    },
    tagging: { current: 0, total: 0, filename: "" },
  };

  let burstTimer = null;
  let burstLeft = 0;
  let suppressBusyPollUntil = 0;

  function pct(current, total) {
    const t = Number(total) || 0;
    const c = Number(current) || 0;
    if (t <= 0) return 0;
    return Math.min(100, Math.round((c / t) * 100));
  }

  function downloadPct(download) {
    if (!download) return 0;
    const explicit = Number(download.percent);
    if (!Number.isNaN(explicit) && explicit >= 0) {
      return Math.min(100, Math.round(explicit));
    }
    const bytesTotal = Number(download.bytes_total) || 0;
    const bytesCurrent = Number(download.bytes_current) || 0;
    const fileTotal = Number(download.total) || 0;
    const fileIndex = Number(download.current) || 0;
    if (bytesTotal > 0 && fileTotal > 0) {
      const fileFrac = bytesCurrent / bytesTotal;
      return Math.min(100, Math.round(((fileIndex - 1) + fileFrac) / fileTotal * 100));
    }
    return pct(fileIndex, fileTotal);
  }

  function fileDownloadPct(download) {
    const bytesTotal = Number(download.bytes_total) || 0;
    const bytesCurrent = Number(download.bytes_current) || 0;
    if (bytesTotal > 0) {
      return Math.min(100, Math.round((bytesCurrent / bytesTotal) * 100));
    }
    return 0;
  }

  function formatBytesPair(bytesCurrent, bytesTotal) {
    const cur = Number(bytesCurrent) || 0;
    const tot = Number(bytesTotal) || 0;
    if (tot <= 0) return "";
    const mb = 1024 * 1024;
    if (tot >= mb) {
      return (cur / mb).toFixed(1) + "MB/" + (tot / mb).toFixed(1) + "MB";
    }
    if (tot >= 1024) {
      return Math.round(cur / 1024) + "KB/" + Math.round(tot / 1024) + "KB";
    }
    return cur + "B/" + tot + "B";
  }

  function toast(kind, text) {
    try {
      if (typeof ElMessage !== "undefined") {
        if (kind === "success" && ElMessage.success) ElMessage.success(text);
        else if (kind === "error" && ElMessage.error) ElMessage.error(text);
        else if (ElMessage.info) ElMessage.info(text);
      }
    } catch (e) {
      /* ignore */
    }
  }

  function getFormRoot() {
    return document.querySelector(".schema-container form");
  }

  function readSelectValue(selectRoot) {
    if (!selectRoot) return "";
    const item = selectRoot.querySelector(".el-select__selected-item span");
    if (item && item.textContent) return item.textContent.trim();
    const input = selectRoot.querySelector("input");
    return input && input.value ? input.value.trim() : "";
  }

  function readInputValue(item) {
    const inputs = item.querySelectorAll(
      "input.el-input__inner, textarea.el-textarea__inner, input:not([type='checkbox']):not([type='radio']):not([type='hidden'])"
    );
    for (let i = 0; i < inputs.length; i++) {
      const v = String(inputs[i].value || "").trim();
      if (v) return v;
    }
    return "";
  }

  function itemMeta(item) {
    const label = ((item.querySelector(".el-form-item__label") || {}).textContent || "").trim();
    const desc = ((item.querySelector(".el-form-item__description") || {}).textContent || "").trim();
    const norm = label.replace(/\s+/g, "");
    const blob = (label + " " + desc).replace(/\s+/g, "");
    return { label, norm, blob };
  }

  function looksLikePath(value) {
    if (!value || value.length < 2) return false;
    return value.indexOf(":\\") >= 0 || value.indexOf(":/") >= 0 || value.indexOf("/") >= 0 || value.indexOf("\\") >= 0;
  }

  function findPathFallback(form) {
    const inputs = form.querySelectorAll("input.el-input__inner, textarea.el-textarea__inner");
    for (let i = 0; i < inputs.length; i++) {
      const v = String(inputs[i].value || "").trim();
      if (looksLikePath(v)) return v;
    }
    return "";
  }

  function readSwitchValue(item) {
    const sw = item.querySelector(".el-switch");
    if (!sw) return null;
    return sw.classList.contains("is-checked");
  }

  function readSliderValue(item) {
    const input = item.querySelector(".el-input-number input, input[type='number']");
    if (input && input.value !== "") return parseFloat(input.value);
    const label = item.querySelector(".el-form-item__label");
    const show = item.querySelector(".el-slider__button-wrapper");
    if (show && label) {
      const hidden = item.querySelector("input[type='hidden'], input[aria-valuenow]");
      if (hidden && hidden.getAttribute("aria-valuenow")) {
        return parseFloat(hidden.getAttribute("aria-valuenow"));
      }
    }
    return null;
  }

  function readRadioSelectValue(item) {
    const checked = item.querySelector(".el-radio.is-checked .el-radio__label");
    if (checked) return checked.textContent.trim();
    const sel = readSelectValue(item.querySelector(".el-select"));
    if (sel) return sel;
    return "";
  }

  function readNativeSelectValue(item) {
    const select = item.querySelector("select");
    if (!select) return "";
    return String(select.value || "").trim();
  }

  function mapConflictLabel(text) {
    if (text.indexOf("忽略") >= 0 || text === "ignore") return "ignore";
    if (text.indexOf("覆盖") >= 0 || text.indexOf("复制") >= 0 || text === "copy") return "copy";
    if (text.indexOf("前") >= 0 || text === "prepend") return "prepend";
    return "copy";
  }

  function collectTaggerForm() {
    const form = getFormRoot();
    const payload = {
      interrogator_model: "wd14-convnextv2-v2",
      path: "",
      threshold: 0.35,
      character_threshold: 0.6,
      add_rating_tag: false,
      add_model_tag: false,
      additional_tags: "",
      download_endpoint: "",
      exclude_tags: "",
      escape_tag: true,
      batch_input_recursive: false,
      batch_output_action_on_conflict: "copy",
      replace_underscore: true,
      replace_underscore_excludes:
        "0_0, (o)_(o), +_+, +_-, ._., <o>_<o>, <|>_<|>, =_=, >_<, 3_3, 6_9, >_o, @_@, ^_^, o_o, u_u, x_x, |_|, ||_||",
    };

    if (!form) return payload;

    payload.interrogator_model = readSelectValue(form.querySelector(".el-select")) || payload.interrogator_model;

    const items = form.querySelectorAll(".el-form-item");
    items.forEach(function (item) {
      const meta = itemMeta(item);
      const key = meta.norm;
      const blob = meta.blob;

      if (key === "path" || blob.indexOf("图片文件夹") >= 0) {
        payload.path = readInputValue(item);
      } else if (key === "interrogator_model" || blob.indexOf("Tagger模型") >= 0) {
        const v = readSelectValue(item.querySelector(".el-select")) || readInputValue(item);
        if (v) payload.interrogator_model = v;
      } else if (key === "threshold" || (blob.indexOf("阈值") >= 0 && blob.indexOf("角色") < 0)) {
        const v = readSliderValue(item);
        if (v !== null && !Number.isNaN(v)) payload.threshold = v;
      } else if (key === "character_threshold" || blob.indexOf("角色名称") >= 0) {
        const v = readSliderValue(item);
        if (v !== null && !Number.isNaN(v)) payload.character_threshold = v;
      } else if (key === "add_rating_tag" || blob.indexOf("等级标签") >= 0) {
        const v = readSwitchValue(item);
        if (v !== null) payload.add_rating_tag = v;
      } else if (key === "add_model_tag" || blob.indexOf("模型标签") >= 0) {
        const v = readSwitchValue(item);
        if (v !== null) payload.add_model_tag = v;
      } else if (key === "additional_tags" || blob.indexOf("附加提示词") >= 0) {
        payload.additional_tags = readInputValue(item);
      } else if (key === "download_endpoint" || blob.indexOf("模型下载加速源") >= 0) {
        payload.download_endpoint = readRadioSelectValue(item) || readNativeSelectValue(item);
      } else if (key === "replace_underscore" || blob.indexOf("空格代替下划线") >= 0) {
        const v = readSwitchValue(item);
        if (v !== null) payload.replace_underscore = v;
      } else if (key === "escape_tag" || blob.indexOf("括号") >= 0 || blob.indexOf("转义") >= 0) {
        const v = readSwitchValue(item);
        if (v !== null) payload.escape_tag = v;
      } else if (key === "batch_input_recursive" || blob.indexOf("递归搜索") >= 0) {
        const v = readSwitchValue(item);
        if (v !== null) payload.batch_input_recursive = v;
      } else if (
        key === "batch_output_action_on_conflict" ||
        blob.indexOf("已经存在") >= 0 ||
        blob.indexOf("Tag文件") >= 0
      ) {
        const t = readRadioSelectValue(item);
        if (t) payload.batch_output_action_on_conflict = mapConflictLabel(t);
      }
    });

    if (!payload.path) payload.path = findPathFallback(form);
    if (payload.path) payload.path = payload.path.replaceAll("\\", "/");
    return payload;
  }

  function getInterrogatorModel() {
    return collectTaggerForm().interrogator_model;
  }

  function statusInnerHtml() {
    return (
      '<div class="sd-tagger-dock__status-line">' +
      '<span class="sd-tagger-dock__phase" data-phase>空闲</span>' +
      '<span class="sd-tagger-dock__message" data-status-message>配置参数后点击启动</span>' +
      '<button type="button" class="sd-tagger-dock__link" data-prefetch-btn>预下载</button>' +
      "</div>" +
      '<div class="sd-tagger-dock__meters" data-meters>' +
      '<div class="sd-tagger-dock__meter" data-block="download">' +
      '<div class="sd-tagger-dock__meter-head"><span>模型下载</span><span data-download-meta>—</span></div>' +
      '<div class="sd-tagger-dock__track"><div class="sd-tagger-dock__fill sd-tagger-dock__fill--download" data-download-bar></div></div>' +
      "</div>" +
      '<div class="sd-tagger-dock__meter" data-block="tagging">' +
      '<div class="sd-tagger-dock__meter-head"><span>打标</span><span data-tagging-meta>—</span></div>' +
      '<div class="sd-tagger-dock__track"><div class="sd-tagger-dock__fill sd-tagger-dock__fill--tagging" data-tagging-bar></div></div>' +
      "</div></div>" +
      '<div class="sd-tagger-dock__buttons">' +
      '<button type="button" class="el-button max-btn color-btn el-button--primary is-plain sd-tagger-dock__start" data-start-btn>启动</button>' +
      '<button type="button" class="el-button max-btn sd-tagger-dock__reset" data-reset-btn>重置</button>' +
      "</div>"
    );
  }

  function setPending(message) {
    const dock = document.getElementById("sd-tagger-dock");
    if (dock) dock.classList.add("sd-tagger-dock--pending");
    applyStatus({
      phase: "pending",
      message: message,
      download: { current: 0, total: 0, filename: "" },
      tagging: { current: 0, total: 0, filename: "" },
    });
  }

  function clearPending() {
    document.getElementById("sd-tagger-dock")?.classList.remove("sd-tagger-dock--pending");
  }

  function isTaskActive(phase) {
    return phase === "downloading" || phase === "tagging" || phase === "pending";
  }

  function isPrefetchCancelMode(phase) {
    return phase === "downloading" || phase === "pending";
  }

  function forceIdleDock(message) {
    const payload = Object.assign({}, IDLE_DOCK, {
      message: message || IDLE_DOCK.message,
    });
    applyStatus(payload);
    if (burstTimer) {
      clearInterval(burstTimer);
      burstTimer = null;
      burstLeft = 0;
    }
  }

  function updateStartButton(dock, phase) {
    const btn = dock?.querySelector("[data-start-btn]");
    if (!btn) return;
    if (isTaskActive(phase)) {
      btn.textContent = "中止";
      btn.classList.add("sd-tagger-dock__start--cancel");
      btn.removeAttribute("disabled");
    } else {
      btn.textContent = "启动";
      btn.classList.remove("sd-tagger-dock__start--cancel");
      btn.classList.remove("is-loading");
    }
  }

  function updatePrefetchButton(dock, phase) {
    const link = dock?.querySelector("[data-prefetch-btn]");
    if (!link) return;
    if (isPrefetchCancelMode(phase)) {
      link.textContent = "中止";
      link.classList.add("sd-tagger-dock__link--cancel");
      link.removeAttribute("disabled");
    } else {
      link.textContent = "预下载";
      link.classList.remove("sd-tagger-dock__link--cancel");
      link.classList.remove("is-loading");
      if (phase === "tagging") link.setAttribute("disabled", "");
      else link.removeAttribute("disabled");
    }
  }

  function isTaggerPage() {
    return /tagger/i.test(location.pathname || "");
  }

  function dockHasButtons() {
    const dock = document.getElementById("sd-tagger-dock");
    return !!(dock && dock.querySelector("[data-start-btn]"));
  }

  function ensureRefreshHint() {
    if (!isTaggerPage()) return;
    const content = document.querySelector(".example-container > .right-container .theme-default-content main > div");
    if (!content) return;
    if (content.querySelector("[data-tagger-refresh-hint]")) return;
    const hint = document.createElement("p");
    hint.setAttribute("data-tagger-refresh-hint", "1");
    hint.textContent = "提示：若未看到下载/打标进度或按钮样式更新，请按 Ctrl+F5 强制刷新页面。";
    hint.style.margin = "0.35rem 0 0.7rem";
    hint.style.fontSize = "12px";
    hint.style.color = "var(--c-text-lighter, #909399)";
    hint.style.lineHeight = "1.55";
    const sectionTitle = content.querySelector("h3");
    if (sectionTitle && sectionTitle.parentElement === content) content.insertBefore(hint, sectionTitle);
    else content.appendChild(hint);
  }

  function ensureDock() {
    if (!isTaggerPage()) return null;

    const right = document.querySelector(".example-container > .right-container");
    if (!right) return null;

    let dock = document.getElementById("sd-tagger-dock");
    if (!dock || !right.contains(dock)) {
      if (dock && dock.parentElement) dock.remove();
      dock = document.createElement("footer");
      dock.id = "sd-tagger-dock";
      dock.className = "sd-tagger-dock sd-tagger-dock--idle";
      dock.setAttribute("aria-label", "打标操作区");
      dock.innerHTML = statusInnerHtml();
      right.appendChild(dock);
    }

    let btnWrap = dock.querySelector(".sd-tagger-dock__buttons");
    if (!btnWrap) {
      btnWrap = document.createElement("div");
      btnWrap.className = "sd-tagger-dock__buttons";
      dock.appendChild(btnWrap);
    }
    if (!btnWrap.querySelector("[data-start-btn]")) {
      btnWrap.innerHTML =
        '<button type="button" class="el-button max-btn color-btn el-button--primary is-plain sd-tagger-dock__start" data-start-btn>启动</button>' +
        '<button type="button" class="el-button max-btn sd-tagger-dock__reset" data-reset-btn>重置</button>';
    }

    // JS 兜底隐藏 Vue 原始按钮，避免依赖 :has 选择器兼容性
    const legacyButtons = right.querySelectorAll(":scope > button.el-button");
    for (let i = 0; i < legacyButtons.length; i++) {
      legacyButtons[i].style.display = "none";
    }

    return dock;
  }

  let mountScheduled = false;
  function scheduleMount() {
    if (!isTaggerPage()) return;
    if (mountScheduled) return;
    mountScheduled = true;
    requestAnimationFrame(function () {
      mountScheduled = false;
      ensureDock();
    });
  }

  function formatStatusMessage(data) {
    const phase = data.phase || "idle";
    const tagging = data.tagging || {};
    const total = Number(tagging.total) || 0;
    const current = Number(tagging.current) || 0;
    const raw = (data.message || "").trim();

    if (phase === "done") {
      if (total > 0) return "已完成 " + current + " / " + total + " 张";
      if (raw && raw !== "打标完成") return raw;
      return "打标已完成";
    }
    if (phase === "tagging" && total > 0) {
      return "正在打标 " + current + " / " + total + " 张…";
    }
    if (phase === "downloading") {
      if (raw && raw.indexOf("正在下载模型") >= 0) return raw;
      const download = data.download || {};
      const fn = download.filename || "";
      const filePct = fileDownloadPct(download);
      const overallPct = downloadPct(download);
      const sizeHint = formatBytesPair(download.bytes_current, download.bytes_total);
      if (fn) {
        let line = "正在下载模型 " + fn;
        if (filePct > 0) line += " " + filePct + "%";
        if (sizeHint) line += "（" + sizeHint;
        if (sizeHint && (Number(download.total) || 0) > 1) {
          line += "，总进度 " + overallPct + "%";
        }
        if (sizeHint) line += "）";
        return line;
      }
      return raw || "正在下载模型，完成后自动打标…";
    }
    if (phase === "error") return raw || "任务失败";
    if (phase === "cancelling") return raw || "正在中止…";
    if (phase === "pending") return raw || "处理中…";
    if (raw) return raw;
    return "配置参数后点击启动";
  }

  function formatMeterMeta(block, data) {
    const phase = data.phase || "idle";
    if (block === "tagging") {
      const tagging = data.tagging || {};
      const total = Number(tagging.total) || 0;
      const current = Number(tagging.current) || 0;
      if (total <= 0) return "—";
      if (phase === "done") return current + " / " + total;
      return pct(current, total) + "% · " + current + "/" + total;
    }
    const download = data.download || {};
    const fileTotal = Number(download.total) || 0;
    const fileIndex = Number(download.current) || 0;
    if (fileTotal <= 0) return "—";
    const filePct = fileDownloadPct(download);
    const overallPct = downloadPct(download);
    const sizeHint = formatBytesPair(download.bytes_current, download.bytes_total);
    if (filePct > 0 && sizeHint) {
      if (fileTotal > 1) return filePct + "% · " + sizeHint + " · 总 " + overallPct + "%";
      return filePct + "% · " + sizeHint;
    }
    return overallPct + "% · 文件 " + fileIndex + "/" + fileTotal;
  }

  function applyStatus(data) {
    const dock = ensureDock();
    if (!dock || !data) return;

    const phase = data.phase || "idle";
    if (Date.now() < suppressBusyPollUntil) {
      if (phase === "downloading" || phase === "tagging") return;
      if (phase === "idle" || phase === "cancelling" || phase === "error") {
        suppressBusyPollUntil = 0;
      }
    }
    const busy =
      phase === "downloading" || phase === "tagging" || phase === "pending" || phase === "cancelling";

    if (phase !== "pending") clearPending();

    dock.classList.toggle(
      "sd-tagger-dock--busy",
      phase === "downloading" || phase === "tagging" || phase === "cancelling"
    );
    dock.classList.toggle("sd-tagger-dock--downloading", phase === "downloading");
    dock.classList.toggle("sd-tagger-dock--idle", phase === "idle");
    dock.classList.toggle("sd-tagger-dock--done", phase === "done");
    dock.classList.toggle("sd-tagger-dock--error", phase === "error");
    dock.dataset.phase = phase;

    const phaseEl = dock.querySelector("[data-phase]");
    if (phaseEl) {
      phaseEl.textContent = PHASE_LABEL[phase] || phase;
      phaseEl.dataset.phase = phase;
    }

    const download = data.download || {};
    const tagging = data.tagging || {};
    const dBar = dock.querySelector("[data-download-bar]");
    const tBar = dock.querySelector("[data-tagging-bar]");
    const dPct = downloadPct(download);
    const tPct = pct(tagging.current, tagging.total);
    if (dBar) {
      const isIndeterminateDownload = phase === "downloading" && dPct <= 0;
      dBar.classList.toggle("is-indeterminate", isIndeterminateDownload);
      dBar.style.width = (isIndeterminateDownload ? 100 : dPct) + "%";
    }
    if (tBar) tBar.style.width = tPct + "%";
    dock.style.setProperty("--sd-tagger-progress", String(phase === "downloading" ? dPct : tPct));

    const dMeta = dock.querySelector("[data-download-meta]");
    const tMeta = dock.querySelector("[data-tagging-meta]");
    if (dMeta) dMeta.textContent = formatMeterMeta("download", data);
    if (tMeta) tMeta.textContent = formatMeterMeta("tagging", data);

    const msg = dock.querySelector("[data-status-message]");
    if (msg) msg.textContent = formatStatusMessage(data);

    dock.querySelector('[data-block="download"]')?.classList.toggle("is-active", phase === "downloading");
    dock.querySelector('[data-block="tagging"]')?.classList.toggle("is-active", phase === "tagging" || phase === "done" || phase === "pending");

    const meters = dock.querySelector("[data-meters]");
    if (meters) {
      meters.classList.toggle("is-visible", busy);
      meters.classList.toggle("is-compact", phase === "done");
    }

    updateStartButton(dock, phase);
    updatePrefetchButton(dock, phase);

    if (phase === "downloading") {
      if (!burstTimer) startBurstPoll();
      else if (burstLeft < 30) burstLeft = BURST_COUNT;
    }
  }

  async function pollStatus() {
    try {
      const res = await fetch("/api/tagger/status");
      const json = await res.json();
      if (json && json.status === "success" && json.data) {
        applyStatus(json.data);
        return json.data;
      }
    } catch (e) {
      /* backend offline */
    }
    return null;
  }

  function startBurstPoll() {
    burstLeft = BURST_COUNT;
    if (burstTimer) clearInterval(burstTimer);
    burstTimer = setInterval(function () {
      pollStatus();
      burstLeft -= 1;
      if (burstLeft <= 0) {
        clearInterval(burstTimer);
        burstTimer = null;
      }
    }, BURST_POLL_MS);
  }

  async function cancelTask(activeEl) {
    const dock = ensureDock();
    clearPending();
    suppressBusyPollUntil = Date.now() + 10000;
    forceIdleDock("正在中止…");
    toast("info", "正在中止任务…");
    activeEl?.classList.add("is-loading");

    try {
      const res = await fetch("/api/tagger/cancel", { method: "POST" });
      const json = await res.json();
      if (json.status === "success") {
        toast("success", json.message || "已请求中止");
        startBurstPoll();
        const snap = await pollStatus();
        if (!snap || snap.phase === "downloading" || snap.phase === "tagging") {
          applyStatus({ phase: "cancelling", message: "正在中止…" });
        }
      } else {
        toast("error", json.message || "中止失败");
        forceIdleDock("配置参数后点击启动");
      }
    } catch (e) {
      forceIdleDock("无法连接后端");
      toast("error", "无法连接到后端");
    } finally {
      dock?.querySelector("[data-start-btn]")?.classList.remove("is-loading");
      dock?.querySelector("[data-prefetch-btn]")?.classList.remove("is-loading");
    }
  }

  async function prefetchModel() {
    const dock = ensureDock();
    const link = dock?.querySelector("[data-prefetch-btn]");
    const phase = dock?.dataset.phase || "idle";
    if (isPrefetchCancelMode(phase)) {
      await cancelTask(link);
      return;
    }
    if (link?.disabled || link?.classList.contains("is-loading")) return;

    setPending("正在请求预下载…");
    toast("info", "正在预下载模型…");
    if (link) link.classList.add("is-loading");

    try {
      const endpoint = collectTaggerForm().download_endpoint || "";
      const res = await fetch("/api/tagger/prefetch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          interrogator_model: getInterrogatorModel(),
          download_endpoint: endpoint,
        }),
      });
      const json = await res.json();
      if (json.status === "success") {
        toast("success", json.message || "预下载已开始");
        startBurstPoll();
      } else {
        applyStatus({ phase: "error", message: json.message || "预下载失败" });
        toast("error", json.message || "预下载失败");
      }
    } catch (e) {
      applyStatus({ phase: "error", message: "无法连接后端" });
      toast("error", "无法连接到后端");
    } finally {
      link?.classList.remove("is-loading");
    }
  }

  async function startTagging() {
    const dock = ensureDock();
    const btn = dock?.querySelector("[data-start-btn]");
    const phase = dock?.dataset.phase || "idle";
    if (isTaskActive(phase)) {
      await cancelTask(btn);
      return;
    }
    if (btn?.classList.contains("is-loading")) return;

    const payload = collectTaggerForm();
    if (!payload.path) {
      applyStatus({ phase: "error", message: "请先填写图片文件夹路径" });
      toast("error", "请先填写图片文件夹路径");
      return;
    }

    setPending("正在提交打标任务…");
    toast("info", "正在提交打标任务…");
    btn?.classList.add("is-loading");

    try {
      const res = await fetch("/api/interrogate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (json.status === "success") {
        toast("success", json.message || "打标任务已提交");
        applyStatus({ phase: "tagging", message: "打标任务已开始，请稍候…" });
        startBurstPoll();
      } else {
        applyStatus({ phase: "error", message: json.message || "提交失败" });
        toast("error", json.message || "提交失败");
      }
    } catch (e) {
      applyStatus({ phase: "error", message: "无法连接后端" });
      toast("error", "无法连接到后端");
    } finally {
      btn?.classList.remove("is-loading");
    }
  }

  async function resetTaggerForm() {
    suppressBusyPollUntil = 0;
    try {
      const res = await fetch("/api/tagger/reset", { method: "POST" });
      const json = await res.json();
      if (json.status !== "success") {
        toast("error", json.message || "重置状态失败");
      }
    } catch (e) {
      toast("error", "无法连接后端，仅重置本地显示");
    }
    forceIdleDock("配置参数后点击启动");
    await pollStatus();

    const hidden = document.querySelectorAll(".example-container > .right-container > button.el-button");
    for (let i = 0; i < hidden.length; i++) {
      const label = (hidden[i].textContent || "").replace(/\s+/g, "");
      if (label.indexOf("重置") >= 0) {
        hidden[i].click();
        toast("info", "已重置参数");
        return;
      }
    }
    toast("error", "未找到重置控件");
  }

  function onDockClick(ev) {
    const t = ev.target;
    if (!t || !t.closest) return;
    if (t.closest("[data-prefetch-btn]")) {
      ev.preventDefault();
      const dock = document.getElementById("sd-tagger-dock");
      const phase = dock?.dataset.phase || "idle";
      const link = t.closest("[data-prefetch-btn]");
      if (isPrefetchCancelMode(phase)) cancelTask(link);
      else prefetchModel();
      return;
    }
    if (t.closest("[data-start-btn]")) {
      ev.preventDefault();
      const dock = document.getElementById("sd-tagger-dock");
      const phase = dock?.dataset.phase || "idle";
      const btn = t.closest("[data-start-btn]");
      if (isTaskActive(phase)) cancelTask(btn);
      else startTagging();
      return;
    }
    if (t.closest("[data-reset-btn]")) {
      ev.preventDefault();
      resetTaggerForm();
    }
  }

  function boot() {
    if (!isTaggerPage()) return;

    scheduleMount();
    ensureRefreshHint();
    pollStatus();
    setInterval(pollStatus, POLL_MS);
    setInterval(function () {
      if (!dockHasButtons()) scheduleMount();
      ensureRefreshHint();
    }, 800);

    document.addEventListener("click", onDockClick);

    const app = document.getElementById("app");
    if (app) {
      new MutationObserver(scheduleMount).observe(app, { childList: true, subtree: true });
    }
    window.addEventListener("load", scheduleMount);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
