/**
 * Anima Fast plugin install panel: status polling, install trigger, guide toggle.
 * Loaded globally so SPA navigation to /lora/anima-fast works (not only full page load).
 */
(function () {
  if (window.__ANIMA_FAST_INSTALL_GUARD__) return;
  window.__ANIMA_FAST_INSTALL_GUARD__ = true;

  const CONFIRM =
    "Anima Fast 为进阶实验插件，需 NVIDIA GPU、约 16GB+ 显存，并会下载独立 Python 环境（数 GB）。\n\n确认已了解并继续安装？";

  let last = { feature_enabled: true, state: "unknown" };
  let es = null;
  let progressEs = null;
  let tmr = null;
  let scheduled = false;
  let observedPath = location.pathname;
  let progressStartedAt = 0;
  let reconnectedInstallTask = "";
  let installSessionActive = false;
  let reloadScheduled = false;
  const POST_INSTALL_RELOAD_KEY = "anima-fast-post-install-reload";

  function q(sel) {
    return Array.from(document.querySelectorAll(sel));
  }

  function isFastPage() {
    return /^\/lora\/anima-fast(\.html|\.md)?$/.test(location.pathname);
  }

  function markPage() {
    document.body.classList.toggle("anima-fast-page", isFastPage());
  }

  function dedupeInstallPanels(ready) {
    q(".anima-fast-install-panel").forEach(function (panel, index) {
      const duplicateReadyPanel = ready && index > 0;
      panel.hidden = duplicateReadyPanel;
      panel.style.display = duplicateReadyPanel ? "none" : "flex";
    });
  }

  function setControls(d) {
    if (!isFastPage()) return;
    const kill = !d.feature_enabled;
    const working = d.state === "installing" || d.state === "auditing";
    const ready = d.state === "ready";
    dedupeInstallPanels(ready);
    q("[data-anima-fast-progress]").forEach(function (root) {
      root.hidden = ready;
      root.style.display = ready ? "none" : "";
    });
    q("[data-anima-fast-log]").forEach(function (p) {
      if (!ready) return;
      p.hidden = true;
      p.style.display = "none";
    });
    q("[data-anima-fast-install]").forEach(function (b) {
      b.hidden = ready;
      b.style.display = ready ? "none" : "";
      b.disabled = kill || working || ready;
      b.setAttribute("aria-disabled", b.disabled ? "true" : "false");
      b.setAttribute("data-anima-fast-ready", ready ? "1" : "0");
      if (!b.getAttribute("data-anima-fast-original-label")) {
        b.setAttribute("data-anima-fast-original-label", (b.textContent || "").trim());
      }
      const span = b.querySelector("span") || b;
      span.textContent = ready ? label(d) : b.getAttribute("data-anima-fast-original-label");
    });
    q(".right-container button").forEach(function (b) {
      const t = (b.textContent || "").trim();
      if (
        t === "开始训练" ||
        t === "Start training"
      ) {
        b.disabled = kill || !ready;
        b.setAttribute("aria-disabled", b.disabled ? "true" : "false");
        b.setAttribute("data-anima-fast-train-gated", !ready ? "1" : "0");
      }
    });
    document.body.classList.toggle("anima-fast-disabled", kill || !ready);
  }

  function label(d) {
    if (!d.feature_enabled) return "功能已关闭";
    if (d.state === "ready") return "插件已就绪";
    if (d.state === "installing") return "安装中";
    if (d.state === "auditing") return "审计中";
    if (d.state === "broken") return "需修复";
    if (d.state === "installed_unverified") return "待审计";
    return "进阶插件 · 待开启";
  }

  function syncStatusLabels(d) {
    const text = label(d);
    const title =
      d.state === "ready"
        ? "核心可训练依赖齐全；sam3/遮罩等可选依赖按需安装，不影响训练就绪状态。"
        : "";
    q("[data-anima-fast-status]").forEach(function (n) {
      if (n.textContent !== text) n.textContent = text;
      if (n.title !== title) n.title = title;
    });
  }

  function appendLog(x) {
    const p = document.querySelector("[data-anima-fast-log]");
    if (!p) return;
    p.hidden = false;
    p.textContent += (p.textContent ? "\n" : "") + x;
    p.scrollTop = p.scrollHeight;
  }

  function formatEta(seconds) {
    if (!Number.isFinite(seconds) || seconds <= 0) return "正在估算";
    const total = Math.max(1, Math.round(seconds));
    const minutes = Math.floor(total / 60);
    const remain = total % 60;
    if (minutes <= 0) return remain + " 秒";
    if (minutes < 60) return minutes + " 分 " + remain + " 秒";
    const hours = Math.floor(minutes / 60);
    return hours + " 小时 " + (minutes % 60) + " 分";
  }

  function estimateEta(percent) {
    if (!progressStartedAt || percent <= 0 || percent >= 100) return "";
    const elapsed = (Date.now() - progressStartedAt) / 1000;
    return formatEta((elapsed / percent) * (100 - percent));
  }

  function resetProgress() {
    progressStartedAt = Date.now();
    const root = document.querySelector("[data-anima-fast-progress]");
    if (!root) return;
    root.hidden = false;
    const bar = root.querySelector("[data-anima-fast-progress-bar]");
    const text = root.querySelector("[data-anima-fast-progress-text]");
    const meta = root.querySelector("[data-anima-fast-progress-meta]");
    if (bar) bar.style.width = "0%";
    if (text) text.textContent = "准备安装";
    if (meta) meta.textContent = "0% · 预计剩余：正在估算";
  }

  function updateProgress(event) {
    const root = document.querySelector("[data-anima-fast-progress]");
    if (!root || !event) return;
    root.hidden = false;
    const percent = Math.max(0, Math.min(100, Number(event.percent || 0)));
    const bar = root.querySelector("[data-anima-fast-progress-bar]");
    const text = root.querySelector("[data-anima-fast-progress-text]");
    const meta = root.querySelector("[data-anima-fast-progress-meta]");
    if (bar) bar.style.width = percent + "%";
    if (text) text.textContent = event.message || event.phase || "安装中";
    if (meta) {
      const eta = event.eta_seconds != null ? formatEta(Number(event.eta_seconds)) : estimateEta(percent);
      meta.textContent = percent + "% · 阶段：" + (event.phase || "unknown") + (eta ? " · 预计剩余：" + eta : "");
    }
  }

  function showFastTrainBlockedNotice() {
    if (!isFastPage()) return;
    const message = "Anima Fast dependencies are not ready yet. Please install the plugin first.";
    appendLog("[blocked] " + message);
    q("[data-anima-fast-status]").forEach(function (n) {
      n.textContent = message;
      n.title = message;
    });
  }

  function formatFastRunFail(json) {
    if (!json || json.status === "success") return "";
    const parts = [];
    if (json.message) parts.push(String(json.message));
    const errs = json.data && json.data.errors;
    if (Array.isArray(errs)) {
      errs.slice(0, 6).forEach(function (e) {
        const line = String(e || "").trim();
        if (line && parts.indexOf(line) === -1) parts.push(line);
      });
    }
    return parts.join(" | ");
  }

  const COMPILE_WARN_TEXT =
    "compile_mode=full 与「梯度检查点」不能同时开启。已自动调整：请保持 compile 模式为 blocks，或关闭梯度检查点后再选 full。";
  let compileGuardBusy = false;
  let lastCompileWarnShown = false;

  function findFormItem(labelNeedle) {
    return Array.from(document.querySelectorAll(".example-container .el-form-item, .example-container .k-schema-item")).find(function (row) {
      const lab = row.querySelector(".el-form-item__label, .k-schema-main");
      const text = ((lab && lab.textContent) || row.textContent || "").trim();
      return text.indexOf(labelNeedle) !== -1;
    });
  }

  function readSelectText(row) {
    if (!row) return "";
    const item = row.querySelector(".el-select .el-select__selected-item span");
    if (item) return (item.textContent || "").trim();
    const wrap = row.querySelector(".el-select__wrapper, .el-select");
    return wrap ? (wrap.textContent || "").trim() : "";
  }

  function readSwitchOn(row) {
    if (!row) return false;
    const input = row.querySelector('input[type="checkbox"]');
    if (input) return !!input.checked;
    const sw = row.querySelector(".el-switch");
    return sw ? sw.classList.contains("is-checked") : false;
  }

  function auditImports() {
    const audit = last && last.facts && last.facts.audit;
    const facts = audit && audit.facts;
    const anima = facts && facts.anima;
    return (anima && anima.imports) || {};
  }

  function importAvailability(name) {
    const imports = auditImports();
    if (!Object.prototype.hasOwnProperty.call(imports, name)) return null;
    return imports[name] === true;
  }

  function flashUnavailable() {
    return importAvailability("flash_attn") === false;
  }

  function quantoUnavailable() {
    return importAvailability("optimum.quanto") === false;
  }

  function setSwitchOn(row, on) {
    if (!row || readSwitchOn(row) === on) return;
    const sw = row.querySelector(".el-switch");
    if (sw) sw.click();
  }

  function pickSelectOption(row, want) {
    if (!row) return;
    const select = row.querySelector(".el-select");
    if (!select) return;
    if (readSelectText(row) === want) return;
    select.click();
    window.setTimeout(function () {
      const items = Array.from(document.querySelectorAll(".el-select-dropdown__item"));
      const hit = items.find(function (el) {
        return (el.textContent || "").trim() === want;
      });
      if (hit) hit.click();
    }, 60);
  }

  function markUnavailableDropdownOptions() {
    if (!isFastPage()) return;
    const disabled = [];
    if (flashUnavailable()) disabled.push({ text: "flash", reason: "flash-attn 不可用，请先修复插件环境或使用 torch/xformers" });
    if (quantoUnavailable()) disabled.push({ text: "Automagic", reason: "Automagic 需要 optimum-quanto，请先修复插件环境或使用 AdamW8bit" });
    if (!disabled.length) return;
    window.setTimeout(function () {
      q(".el-select-dropdown__item").forEach(function (item) {
        const text = (item.textContent || "").trim();
        const hit = disabled.find(function (entry) {
          return entry.text === text;
        });
        if (!hit) return;
        item.classList.add("anima-fast-option-disabled");
        item.setAttribute("aria-disabled", "true");
        item.setAttribute("title", hit.reason);
        item.setAttribute("data-anima-fast-disabled-reason", hit.reason);
      });
    }, 80);
  }

  function syncAuditOptionGuards() {
    if (!isFastPage()) return;
    const attnRow = findFormItem("Attention 加速实现");
    const optimizerRow = findFormItem("优化器");
    if (flashUnavailable() && readSelectText(attnRow) === "flash") {
      pickSelectOption(attnRow, "torch");
      appendLog("[warning] flash-attn 不可用，已将 Attention 从 flash 改为 torch");
    }
    if (quantoUnavailable() && readSelectText(optimizerRow) === "Automagic") {
      pickSelectOption(optimizerRow, "AdamW8bit");
      appendLog("[warning] optimum-quanto 不可用，已将优化器从 Automagic 改为 AdamW8bit");
    }
    attnRow && attnRow.classList.toggle("anima-fast-audit-limited", flashUnavailable());
    optimizerRow && optimizerRow.classList.toggle("anima-fast-audit-limited", quantoUnavailable());
  }

  function ensureCompileWarnBanner() {
    const form = document.querySelector(".example-container .schema-container .el-form, .example-container .schema-container form");
    if (!form || form.querySelector("[data-anima-fast-compile-warn]")) return;
    const banner = document.createElement("div");
    banner.className = "anima-fast-compile-warn";
    banner.setAttribute("data-anima-fast-compile-warn", "");
    banner.hidden = true;
    banner.textContent = COMPILE_WARN_TEXT;
    form.insertBefore(banner, form.firstChild);
  }

  function showCompileWarn(show) {
    ensureCompileWarnBanner();
    const banner = document.querySelector("[data-anima-fast-compile-warn]");
    if (!banner) return;
    banner.hidden = !show;
    if (show && !lastCompileWarnShown) {
      appendLog("[warning] " + COMPILE_WARN_TEXT);
      lastCompileWarnShown = true;
    }
    if (!show) lastCompileWarnShown = false;
  }

  function syncCompileGuard() {
    if (!isFastPage() || compileGuardBusy) return;
    const compileRow = findFormItem("compile 模式");
    const gcRow = findFormItem("梯度检查点");
    if (!compileRow && !gcRow) return;

    const compileMode = readSelectText(compileRow);
    const gcOn = readSwitchOn(gcRow);
    const conflict = compileMode === "full" && gcOn;

    compileRow && compileRow.classList.toggle("anima-fast-compile-locked", gcOn);
    gcRow && gcRow.classList.toggle("anima-fast-compile-locked", compileMode === "full");

    if (!conflict) {
      showCompileWarn(false);
      return;
    }

    compileGuardBusy = true;
    try {
      if (gcOn && compileMode === "full") {
        pickSelectOption(compileRow, "blocks");
      } else if (compileMode === "full") {
        setSwitchOn(gcRow, false);
      }
      showCompileWarn(true);
    } finally {
      window.setTimeout(function () {
        compileGuardBusy = false;
      }, 120);
    }
  }

  function initCompileModeGuard() {
    if (!isFastPage()) return;
    ensureCompileWarnBanner();
    syncCompileGuard();
  }

  function patchRunRequestBody(init) {
    if (!init || !init.body || typeof init.body !== "string") return init;
    try {
      const cfg = JSON.parse(init.body);
      if (cfg.model_train_type !== "anima-lora-fast") return init;
      if (cfg.attn_mode === "flash" && flashUnavailable()) {
        cfg.attn_mode = "torch";
        appendLog("[warning] 已阻止 flash-attn 不可用组合，Attention 自动改为 torch");
      }
      if (cfg.optimizer_type === "Automagic" && quantoUnavailable()) {
        cfg.optimizer_type = "AdamW8bit";
        appendLog("[warning] 已阻止 Automagic 缺少 optimum-quanto 组合，优化器自动改为 AdamW8bit");
      }
      if (cfg.skip_cache_check && (cfg.cache_latents || cfg.cache_text_encoder_outputs)) {
        cfg.cache_latents = false;
        cfg.cache_text_encoder_outputs = false;
        cfg.skip_cache_check = false;
        appendLog("[warning] 已阻止 cache 与 skip_cache_check 同时开启，相关开关已自动关闭");
      }
      if (cfg.compile_mode === "full" && cfg.gradient_checkpointing) {
        cfg.compile_mode = "blocks";
        const next = Object.assign({}, init, { body: JSON.stringify(cfg) });
        appendLog("[warning] 已阻止 full + 梯度检查点 组合，compile_mode 自动改为 blocks");
        return next;
      }
      return Object.assign({}, init, { body: JSON.stringify(cfg) });
    } catch (_) {}
    return init;
  }

  if (!window.__ANIMA_FAST_RUN_FETCH_PATCH__) {
    window.__ANIMA_FAST_RUN_FETCH_PATCH__ = true;
    const nativeFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
      const url = typeof input === "string" ? input : input && input.url ? input.url : "";
      const isRun =
        url.indexOf("/api/run") !== -1 && init && String(init.method || "GET").toUpperCase() === "POST";
      if (isRun && isFastPage() && init) {
        init = patchRunRequestBody(init);
      }
      return nativeFetch(input, init).then(function (res) {
        if (!isRun || !isFastPage()) return res;
        return res
          .clone()
          .json()
          .then(function (json) {
            if (json && json.status === "fail") {
              const msg = formatFastRunFail(json);
              if (msg) appendLog("[训练] " + msg);
            }
            return res;
          })
          .catch(function () {
            return res;
          });
      });
    };
  }

  function apply(d) {
    last = d || last;
    setControls(last);
    syncStatusLabels(last);
    const a = last.facts && last.facts.audit;
    if (a && !a.ok && a.errors) appendLog("[audit] " + a.errors.join("; "));
    syncAuditOptionGuards();
    maybeReloadAfterInstallReady(last);
  }

  function markInstallSessionActive() {
    installSessionActive = true;
    reloadScheduled = false;
    try {
      sessionStorage.removeItem(POST_INSTALL_RELOAD_KEY);
    } catch (_) {}
  }

  function maybeReloadAfterInstallReady(d) {
    if (!isFastPage()) return;
    if (d.state === "installing" || d.state === "auditing") {
      installSessionActive = true;
      return;
    }
    if (d.state !== "ready" || !installSessionActive || reloadScheduled) return;
    installSessionActive = false;
    try {
      if (sessionStorage.getItem(POST_INSTALL_RELOAD_KEY) === "1") return;
      sessionStorage.setItem(POST_INSTALL_RELOAD_KEY, "1");
    } catch (_) {}
    reloadScheduled = true;
    appendLog("[ready] 安装完成，正在刷新页面以加载参数预览…");
    window.setTimeout(function () {
      location.reload();
    }, 700);
  }

  async function status() {
    if (!isFastPage()) return;
    try {
      const r = await fetch("/api/plugins/anima-lora/status");
      const j = await r.json();
      const d = Object.assign({ feature_enabled: true }, j.data || { state: "unknown" });
      apply(d);
      maybeReconnectInstallLog(d);
    } catch (e) {
      const n = document.querySelector("[data-anima-fast-status]");
      if (n) n.textContent = "状态检查失败";
    }
  }

  function scheduleStatus() {
    if (!isFastPage()) return;
    if (scheduled) return;
    scheduled = true;
    setTimeout(function () {
      scheduled = false;
      const pathChanged = observedPath !== location.pathname;
      observedPath = location.pathname;
      markPage();
      initGuideToggle();
      ensureSidebarFastLink();
      initCompileModeGuard();
      setControls(last);
      if (last.state !== "unknown") syncStatusLabels(last);
      syncAuditOptionGuards();
      if (pathChanged) status();
    }, 120);
  }

  function openLog(url) {
    if (!url || !window.EventSource) return;
    if (es) es.close();
    appendLog("[log] streaming " + url);
    es = new EventSource(url);
    es.onmessage = function (e) {
      try {
        const d = JSON.parse(e.data);
        if (d.text) appendLog(d.text);
        if (d.done) {
          appendLog("[log] done");
          es.close();
          es = null;
          if (tmr) {
            clearInterval(tmr);
            tmr = null;
          }
          status();
        }
      } catch (_) {
        appendLog(e.data);
      }
    };
    es.onerror = function () {
      appendLog("[log] stream disconnected");
      if (es) {
        es.close();
        es = null;
      }
      status();
    };
  }

  function openProgress(url) {
    if (!url || !window.EventSource) return;
    if (progressEs) progressEs.close();
    progressEs = new EventSource(url);
    progressEs.onmessage = function (e) {
      try {
        const d = JSON.parse(e.data);
        if (d.type === "progress") updateProgress(d);
        if (d.done || d.type === "done") {
          if (progressEs) {
            progressEs.close();
            progressEs = null;
          }
          status();
        }
      } catch (_) {
        appendLog("[progress] " + e.data);
      }
    };
    progressEs.onerror = function () {
      appendLog("[progress] stream disconnected");
      if (progressEs) {
        progressEs.close();
        progressEs = null;
      }
    };
  }

  function maybeReconnectInstallLog(d) {
    const taskId = d && d.facts && d.facts.task_id;
    if (!taskId || reconnectedInstallTask === taskId) return;
    if (d.state !== "installing" && d.state !== "auditing") return;
    reconnectedInstallTask = taskId;
    markInstallSessionActive();
    resetProgress();
    appendLog("[log] reconnecting install task " + taskId);
    openLog("/api/plugins/anima-lora/install/log/stream/" + taskId);
    openProgress("/api/plugins/anima-lora/install/progress/stream/" + taskId);
  }

  function initGuideToggle() {
    if (!isFastPage()) return;
    q("[data-anima-fast-guide-toggle]").forEach(function (t) {
      const p = t.closest(".anima-fast-guide-collapsible");
      const b = p && p.querySelector(".anima-fast-dataset-guide__body");
      if (!b) return;
      let o = false;
      try {
        o = localStorage.getItem("anima-fast-guide-open") === "1";
      } catch (_) {}
      b.hidden = !o;
      t.setAttribute("aria-expanded", o ? "true" : "false");
      p.classList.toggle("is-open", o);
    });
  }

  function ensureSidebarFastLink() {
    const sidebar = document.querySelector(".sidebar .sidebar-items");
    if (!sidebar) return;
    if (
      sidebar.querySelector('a[href="/lora/anima-fast.html"]') ||
      sidebar.querySelector('a[href="/lora/anima-fast.md"]')
    ) {
      return;
    }
    const finetune = sidebar.querySelector('a[href="/lora/anima-finetune.md"]');
    const anchorLi = finetune && finetune.closest("li");
    const group = anchorLi && anchorLi.parentElement;
    if (!anchorLi || !group) return;

    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = "/lora/anima-fast.html";
    a.className = "sidebar-item sidebar-heading";
    a.setAttribute("aria-label", "Anima LoRA Fast");
    a.appendChild(document.createTextNode(" Anima Fast "));
    li.appendChild(a);
    anchorLi.insertAdjacentElement("afterend", li);
  }

  document.addEventListener("click", async function (e) {
    const guideBtn = e.target && e.target.closest && e.target.closest("[data-anima-fast-guide-toggle]");
    if (guideBtn && isFastPage()) {
      const p = guideBtn.closest(".anima-fast-guide-collapsible");
      const b = p && p.querySelector(".anima-fast-dataset-guide__body");
      if (b) {
        const o = b.hidden;
        b.hidden = !o;
        guideBtn.setAttribute("aria-expanded", o ? "true" : "false");
        p.classList.toggle("is-open", o);
        try {
          localStorage.setItem("anima-fast-guide-open", o ? "1" : "0");
        } catch (_) {}
      }
      return;
    }

    const installBtn = e.target && e.target.closest && e.target.closest("[data-anima-fast-install]");
    if (!installBtn || !isFastPage()) return;
    if (!last.feature_enabled) return;
    if (last.state === "ready" || installBtn.getAttribute("data-anima-fast-ready") === "1") {
      status();
      return;
    }
    if (!window.confirm(CONFIRM)) return;

    markInstallSessionActive();
    installBtn.disabled = true;
    const statusEl = document.querySelector("[data-anima-fast-status]");
    const logEl = document.querySelector("[data-anima-fast-log]");
    if (logEl) {
      logEl.hidden = false;
      logEl.textContent = "";
    }
    resetProgress();
    if (statusEl) statusEl.textContent = "安装任务启动中";

    try {
      const r = await fetch("/api/plugins/anima-lora/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dry_run: false }),
      });
      const j = await r.json();
      if (j.status !== "success") {
        if (statusEl) statusEl.textContent = j.message || "安装失败";
        appendLog("[error] " + (j.message || "install failed"));
        return;
      }
      const d = j.data || {};
      if (d.already_ready) {
        last = Object.assign({ feature_enabled: true }, d.status || last, { state: "ready" });
        apply(last);
        updateProgress({ type: "progress", phase: "ready", percent: 100, message: "Anima Fast plugin already ready" });
        appendLog("[skip] Anima Fast plugin already ready; no dependency install needed");
        return;
      }
      if (statusEl) statusEl.textContent = "安装中";
      appendLog("[task] " + (d.task_id || "unknown"));
      openLog(
        d.log_stream ||
          d.log_stream_url ||
          (d.task_id ? "/api/plugins/anima-lora/install/log/stream/" + d.task_id : "")
      );
      openProgress(
        d.progress_stream ||
          d.progress_stream_url ||
          (d.task_id ? "/api/plugins/anima-lora/install/progress/stream/" + d.task_id : "")
      );
      if (tmr) clearInterval(tmr);
      tmr = setInterval(status, 2000);
      status();
    } catch (err) {
      if (statusEl) statusEl.textContent = "安装失败";
      appendLog("[error] " + err);
    } finally {
      setTimeout(function () {
        setControls(last);
      }, 250);
    }
  });

  document.addEventListener(
    "change",
    function () {
      if (isFastPage()) syncCompileGuard();
    },
    true
  );
  document.addEventListener(
    "click",
    function (e) {
      if (!isFastPage()) return;
      const disabledItem = e.target && e.target.closest && e.target.closest(".el-select-dropdown__item.anima-fast-option-disabled");
      if (disabledItem) {
        e.preventDefault();
        e.stopPropagation();
        appendLog("[warning] " + (disabledItem.getAttribute("data-anima-fast-disabled-reason") || "该选项当前不可用"));
        return;
      }
      const gatedTrain = e.target && e.target.closest && e.target.closest('[data-anima-fast-train-gated="1"]');
      if (gatedTrain) {
        e.preventDefault();
        e.stopPropagation();
        showFastTrainBlockedNotice();
        return;
      }
      markUnavailableDropdownOptions();
      window.setTimeout(function () {
        syncCompileGuard();
        syncAuditOptionGuards();
        markUnavailableDropdownOptions();
      }, 80);
    },
    true
  );

  new MutationObserver(scheduleStatus).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });

  window.addEventListener("popstate", scheduleStatus);
  window.addEventListener("hashchange", scheduleStatus);

  function recoverEmptySchemaForm() {
    if (!isFastPage()) return;
    const form = document.querySelector(".example-container .schema-container form");
    if (!form || form.querySelector(".k-schema-item,.el-form-item")) return;
    const schemas = localStorage.getItem("schemas") || "";
    if (!schemas.includes("anima-lora-fast")) return;
    if (sessionStorage.getItem("anima-fast-schema-reload") === "1") return;
    sessionStorage.setItem("anima-fast-schema-reload", "1");
    location.reload();
  }

  function boot() {
    markPage();
    initGuideToggle();
    ensureSidebarFastLink();
    syncAuditOptionGuards();
    status();
    setTimeout(recoverEmptySchemaForm, 2500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
  setTimeout(boot, 0);
})();
