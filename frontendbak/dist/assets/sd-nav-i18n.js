/**
 * Sidebar / home hub locale labels when UI is English (en-US).
 * Schema forms use vue-i18n; VuePress sidebar SSR text stays Chinese without this patch.
 */
(function () {
  const STORAGE_KEY = "sd-trainer-ui-locale";

  function readStoredLocale() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "en-US" || stored === "zh-CN") return stored;
    return null;
  }

  // One-time migration: older builds persisted the locale in sessionStorage,
  // which did not survive a browser restart. Promote any legacy value into
  // localStorage once, then drop the sessionStorage copy so there is a single
  // source of truth. Kept out of detectEnglishUI() so detection has no write
  // side effects.
  function migrateLegacyLocale() {
    try {
      if (readStoredLocale()) {
        sessionStorage.removeItem(STORAGE_KEY);
        return;
      }
      const legacy = sessionStorage.getItem(STORAGE_KEY);
      if (legacy === "en-US" || legacy === "zh-CN") {
        localStorage.setItem(STORAGE_KEY, legacy);
      }
      sessionStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      /* storage may be unavailable (private mode); ignore */
    }
  }

  const ZH_TO_EN = {
    训练: "Training",
    "LoRA训练": "LoRA Training",
    "LoRA 训练": "LoRA Training",
    全量微调: "Full Finetune",
    "Anima Fast": "Anima Fast",
    工具与调试: "Tools",
    数据集打标: "Dataset Tagging",
    标签编辑: "Tag Editor",
    原生标签编辑: "Native Tag Editor",
    经典标签编辑: "Legacy Tag Editor",
    "LoRA 脚本工具": "LoRA Scripts",
    帮助: "Help",
    新手上路: "Getting Started",
    训练参数说明: "Training Parameters",
    其他: "More",
    "UI 设置": "UI Settings",
    关于: "About",
    更新日志: "Changelog",
    终端: "Terminal",
    训练终端: "Training Terminal",
    灯泡: "Theme",
    切换颜色模式: "toggle color mode",
    全部: "All",
    部署: "Deploy",
    系统: "System",
    训练监控: "Train Monitor",
    "自动端口 · 实时日志": "Auto port · Live logs",
    "DiT · 主推": "DiT · Recommended",
    "DiT full finetune · 高显存": "DiT full finetune · High VRAM",
    "SDXL Finetune · Dreambooth": "SDXL finetune · Dreambooth",
    "SD1.5 / SDXL LoRA": "SD1.5 / SDXL LoRA",
    "Flux LoRA": "Flux LoRA",
    "下一代训练 WebUI": "Next-gen training WebUI",
    "Anima DiT 全量微调（full finetune）": "Anima DiT full finetune",
    "更新完整 DiT 权重，适合进阶玩家训练，需充足样本与高显存":
      "Updates full DiT weights; for advanced users with enough data and VRAM (~24 GB)",
    "Anima Finetune 专家模式": "Anima Finetune · Expert mode",
    "Anima LoRA 训练 专家模式": "Anima LoRA · Expert mode",
    "Anima DiT 模型 LoRA 训练 专家模式": "Anima LoRA training · Expert mode",
    "Anima DiT 训练入口，使用 Qwen3 + T5 + Anima 专用参数":
      "Anima DiT LoRA entry (Qwen3 + T5 + Anima-specific options)",
    "参数预览": "Parameter preview",
    全部重置: "Reset all",
    保存参数: "Save parameters",
    读取参数: "Load parameters",
    下载配置文件: "Download config",
    导入配置文件: "Import config",
    "✨加载训练预设✨": "Load training preset",
    开始训练: "Start training",
    终止训练: "Stop training",
    "帮助 → 新手上路": "Help → Getting started",
    "秋叶用户迁移说明": "Migration from Akiba lora-scripts",
    参数释义: "Parameter glossary",
    标准模式: "Standard mode",
    "Fast 模式": "Fast mode",
    训练用模型: "Training model",
    "Anima Fast 参数": "Anima Fast options",
    数据集设置: "Dataset settings",
    保存设置: "Save settings",
    日志与监控: "Logging & monitoring",
    训练相关参数: "Training options",
    学习率与优化器设置: "Learning rate & optimizer",
    训练预览图设置: "Sample preview settings",
    网络设置: "Network settings",
    "Anima 专用参数": "Anima-specific options",
    日志设置: "Logging settings",
    "caption（Tag）选项": "Caption (tag) options",
    噪声设置: "Noise settings",
    数据增强: "Data augmentation",
    其他设置: "Other settings",
    速度优化选项: "Speed optimization",
    调试选项: "Debug options",
    分布式训练: "Distributed training",
    "Anima LoRA · Fast 模式": "Anima LoRA · Fast mode",
    "Anima 高速 LoRA 训练（进阶插件）。需单独安装 runtime，仅支持标准 LoRA。显存建议 16GB+，首次安装需下载数 GB 依赖。":
      "Anima high-speed LoRA training (advanced plugin). Requires a separate runtime, supports standard LoRA only, recommends 16GB+ VRAM, and downloads several GB of dependencies on first install.",
    "Fast 训练引擎来自开源项目": "Fast training engine from the open-source project",
    "感谢原作者与社区的开发与分享；本页以可选插件形式集成，遵循各自开源许可。":
      "Thanks to the original author and community; this page integrates it as an optional plugin and follows the respective open-source licenses.",
    "Fast 模式训练教程": "Fast mode training guide",
    "（安装、数据路径、故障排除）": "(install, dataset paths, troubleshooting)",
    "标准 Kohya 模式": "Standard Kohya mode",
    "标准模式（Kohya）见 /lora/sd3.html": "Standard mode (Kohya): /lora/sd3.html",
    "数据集路径说明（与 Kohya 不同）": "Dataset path notes (different from Kohya)",
    "Fast 训练": "Fast training",
    "实际读取 resized 目录": "actually reads the resized directory",
    "里的 bucket 预处理图，不是直接读原图。": "bucket-preprocessed images instead of the original images.",
    "训练图片目录": "Training image directory",
    "原图 + caption（如": "Original images + captions (for example",
    "子文件夹": "subfolder",
    "resized 目录": "resized directory",
    "训练真正用到的 bucket PNG；": "Bucket PNGs used for training;",
    留空: "leave blank",
    "时自动写入": "to auto-write to",
    "数据集路径": "dataset path",
    "同一数据集可复用": "reusable for the same dataset",
    "可以填同一路径吗？": "Can both paths be the same?",
    "可以。若该目录已是 bucket 预处理后的 PNG + caption，两处可填":
      "Yes. If the directory already contains bucket-preprocessed PNGs and captions, both fields can use the",
    相同路径: "same path",
    "输出 / cache 目录不存在时会自动创建。左侧「cache_latents」等保持关闭，除非已完成完整 preprocess。":
      "Output/cache directories are created automatically. Keep cache_latents and similar options off unless a full preprocess has already completed.",
    开启插件: "Enable plugin",
    检查中: "Checking",
    功能已关闭: "Disabled",
    插件已就绪: "Plugin ready",
    安装中: "Installing",
    审计中: "Auditing",
    需修复: "Repair needed",
    待审计: "Audit pending",
    "进阶插件 · 待开启": "Advanced plugin · not enabled",
    状态检查失败: "Status check failed",
    安装任务启动中: "Starting install task",
    安装失败: "Install failed",
  };

  const EN_TO_ZH = Object.fromEntries(
    Object.entries(ZH_TO_EN).map(([zh, en]) => [en, zh])
  );
  const TERMINAL_MENU_PATH = "/task.html";
  const TERMINAL_PANEL_ID = "sd-terminal-panel";
  const TERMINAL_STYLE_ID = "sd-terminal-style";
  const ANIMA_LOKR_GUARD_ID = "sd-anima-lokr-config-guard";
  const ANIMA_LOKR_GUARD_PATH = "/assets/anima-lokr-config-guard.js?v=20260722-issue186";

  let terminalPollTimer = null;
  let terminalInstallEs = null;
  let terminalTrainEs = null;
  let terminalInstallTaskId = "";
  let terminalTrainTaskId = "";
  const terminalLogStore = { items: [] };
  const terminalMetricStore = { epoch: "--", speed: "--" };
  let terminalFilter = "all";
  let terminalHintInstallTaskId = "";

  function normalize(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }

  function resolveI18nLocale() {
    try {
      const app = document.querySelector("#app")?.__vue_app__;
      const i18n = app?.config?.globalProperties?.$i18n;
      const loc = i18n?.locale;
      if (typeof loc === "string") return loc;
      if (loc && typeof loc.value === "string") return loc.value;
    } catch (e) {
      /* ignore */
    }
    return null;
  }

  function detectEnglishUI() {
    const stored = readStoredLocale();
    if (stored === "en-US") return true;
    if (stored === "zh-CN") return false;

    const browserLocales = [
      ...(Array.isArray(navigator.languages) ? navigator.languages : []),
      navigator.language,
      navigator.userLanguage,
    ]
      .filter(Boolean)
      .map((loc) => String(loc).toLowerCase());
    if (browserLocales.some((loc) => loc.startsWith("en"))) return true;
    if (browserLocales.some((loc) => loc.startsWith("zh"))) return false;

    const i18nLoc = resolveI18nLocale();
    if (i18nLoc) return i18nLoc.toLowerCase().startsWith("en");

    const htmlLang = (document.documentElement.lang || "").toLowerCase();
    if (htmlLang.startsWith("en")) return true;
    if (htmlLang.startsWith("zh")) return false;

    const trainSpan = document.querySelector(
      ".el-button.el-button--primary.is-plain span, .el-button.el-button--primary span"
    );
    const trainText = normalize(trainSpan?.textContent);
    if (/^start\s*training$/i.test(trainText)) return true;
    if (trainText.includes("开始训练")) return false;

    return true;
  }

  function setNodeText(node, text) {
    if (!node || node.nodeType !== Node.TEXT_NODE) return;
    const cur = normalize(node.textContent);
    if (!cur) return;
    node.textContent = " " + text + " ";
  }

  function replaceInElement(el, map) {
    if (!el) return;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const raw = normalize(node.textContent);
      if (!raw) continue;
      if (map[raw]) {
        setNodeText(node, map[raw]);
        continue;
      }
      for (const [from, to] of Object.entries(map)) {
        if (raw.includes(from) && from.length > 2) {
          node.textContent = node.textContent.split(from).join(to);
          break;
        }
      }
    }
    el.querySelectorAll("[aria-label]").forEach((a) => {
      const label = normalize(a.getAttribute("aria-label"));
      if (map[label]) a.setAttribute("aria-label", map[label]);
    });
    el.querySelectorAll("[title]").forEach((a) => {
      const title = normalize(a.getAttribute("title"));
      if (map[title]) a.setAttribute("title", map[title]);
    });
  }

  function isTerminalPage() {
    return /^\/task(\.html|\.md)?$/i.test(location.pathname || "");
  }

  function ensureAnimaLokrConfigGuard() {
    if (!/^\/lora\/sd3(?:\.(?:html|md))?\/?$/i.test(location.pathname || "")) return;
    if (window.mikazukiAnimaLokrGuardLoaded) return;
    if (document.getElementById(ANIMA_LOKR_GUARD_ID)) return;
    const script = document.createElement("script");
    script.id = ANIMA_LOKR_GUARD_ID;
    script.src = ANIMA_LOKR_GUARD_PATH;
    document.head.appendChild(script);
  }

  function closeTerminalStreams() {
    if (terminalInstallEs) {
      terminalInstallEs.close();
      terminalInstallEs = null;
    }
    if (terminalTrainEs) {
      terminalTrainEs.close();
      terminalTrainEs = null;
    }
  }

  function stopTerminalPolling() {
    if (terminalPollTimer) {
      clearInterval(terminalPollTimer);
      terminalPollTimer = null;
    }
  }

  function ensureSidebarTerminalLink() {
    const sidebar = document.querySelector(".sidebar .sidebar-items");
    if (!sidebar) return;
    if (
      sidebar.querySelector('a[href="/task.html"]') ||
      sidebar.querySelector('a[href="/task.md"]')
    ) {
      return;
    }

    let othersGroup = null;
    sidebar.querySelectorAll("li").forEach((li) => {
      if (othersGroup) return;
      const heading = li.querySelector(":scope > p.sidebar-item.sidebar-heading");
      if (!heading) return;
      const text = normalize(heading.textContent);
      if (text === "其他" || text === "More") {
        othersGroup = li.querySelector(":scope > ul.sidebar-item-children");
      }
    });
    if (!othersGroup) return;

    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = TERMINAL_MENU_PATH;
    a.className = "sidebar-item";
    a.setAttribute("aria-label", "终端");
    a.appendChild(document.createTextNode(" 终端 "));
    li.appendChild(a);
    othersGroup.appendChild(li);
  }

  function setSidebarAnchorLabel(anchor, text) {
    if (!anchor) return;
    anchor.setAttribute("aria-label", text);
    const textNodes = Array.from(anchor.childNodes).filter((node) => node.nodeType === Node.TEXT_NODE);
    const textNode = textNodes[0];
    textNodes.slice(1).forEach((node) => node.remove());
    if (textNode) {
      textNode.textContent = " " + text + " ";
    } else {
      anchor.appendChild(document.createTextNode(" " + text + " "));
    }
  }

  function ensureTagEditorLinks() {
    const sidebar = document.querySelector(".sidebar .sidebar-items");
    if (!sidebar) return;
    const legacy =
      sidebar.querySelector('a[href="/tageditor.md"]') ||
      sidebar.querySelector('a[href="/tageditor.html"]');
    const native = sidebar.querySelector('a[href="/native-tageditor.html"]');
    native?.closest("li")?.remove();
    if (legacy) {
      setSidebarAnchorLabel(legacy, "经典标签编辑");
      if (location.pathname === "/native-tageditor.html") {
        legacy.classList.remove("active");
      }
    }
  }

  function ensureTerminalStyle() {
    if (document.getElementById(TERMINAL_STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = TERMINAL_STYLE_ID;
    style.textContent = `
#${TERMINAL_PANEL_ID} {
  margin: 12px 16px;
  border: 1px solid #dde3ee;
  border-radius: 12px;
  background: #f8fafc;
  box-shadow: 0 8px 30px rgba(15, 23, 42, 0.08);
}
#${TERMINAL_PANEL_ID} .sd-terminal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid #e5eaf3;
}
#${TERMINAL_PANEL_ID} .sd-terminal-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
#${TERMINAL_PANEL_ID} .sd-terminal-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #4f46e5;
  box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.14);
}
#${TERMINAL_PANEL_ID} .sd-terminal-title-sub {
  margin-left: 6px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  color: #4f46e5;
  background: rgba(79, 70, 229, 0.12);
}
#${TERMINAL_PANEL_ID} .sd-terminal-filters {
  display: flex;
  gap: 8px;
}
#${TERMINAL_PANEL_ID} .sd-filter-chip {
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  padding: 4px 10px;
  cursor: pointer;
  background: #fff;
  color: #475569;
  font-size: 12px;
}
#${TERMINAL_PANEL_ID} .sd-filter-chip.active {
  border-color: #6366f1;
  color: #3730a3;
  background: #eef2ff;
}
#${TERMINAL_PANEL_ID} .sd-terminal-body {
  padding: 14px 16px 16px;
}
#${TERMINAL_PANEL_ID} .sd-terminal-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}
#${TERMINAL_PANEL_ID} .sd-card {
  background: #fff;
  border: 1px solid #dbe2ef;
  border-radius: 10px;
  padding: 10px;
}
#${TERMINAL_PANEL_ID} .sd-card-label {
  font-size: 11px;
  color: #64748b;
  margin-bottom: 6px;
}
#${TERMINAL_PANEL_ID} .sd-card-value {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}
#${TERMINAL_PANEL_ID} .sd-terminal-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
#${TERMINAL_PANEL_ID} .sd-summary-item {
  background: #fff;
  border: 1px solid #dbe2ef;
  border-radius: 10px;
  padding: 10px;
}
#${TERMINAL_PANEL_ID} .sd-summary-item b {
  display: block;
  font-size: 11px;
  color: #64748b;
  margin-bottom: 5px;
}
#${TERMINAL_PANEL_ID} .sd-summary-item code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  color: #0f172a;
  word-break: break-all;
}
#${TERMINAL_PANEL_ID} .sd-terminal-meta {
  color: #64748b;
  font-size: 12px;
  margin-bottom: 6px;
}
#${TERMINAL_PANEL_ID} .sd-terminal-shell {
  border: 1px solid #1f2937;
  border-radius: 12px;
  background: radial-gradient(circle at top right, #192238 0%, #0a1020 45%, #050914 100%);
  padding: 0;
  overflow: hidden;
}
#${TERMINAL_PANEL_ID} .sd-shell-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}
#${TERMINAL_PANEL_ID} .sd-shell-dots {
  display: flex;
  gap: 6px;
}
#${TERMINAL_PANEL_ID} .sd-shell-dots span {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  display: inline-block;
}
#${TERMINAL_PANEL_ID} .sd-shell-dots span:nth-child(1) { background: #fb7185; }
#${TERMINAL_PANEL_ID} .sd-shell-dots span:nth-child(2) { background: #facc15; }
#${TERMINAL_PANEL_ID} .sd-shell-dots span:nth-child(3) { background: #34d399; }
#${TERMINAL_PANEL_ID} .sd-shell-title {
  color: #94a3b8;
  font-size: 11px;
}
#${TERMINAL_PANEL_ID} .sd-terminal-log {
  margin: 0;
  min-height: 420px;
  max-height: 62vh;
  overflow: auto;
  padding: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.45;
  color: #dbeafe;
  white-space: pre-wrap;
}
#${TERMINAL_PANEL_ID} .sd-log-line {
  margin: 0;
}
#${TERMINAL_PANEL_ID} .sd-log-line + .sd-log-line {
  margin-top: 2px;
}
#${TERMINAL_PANEL_ID} .sd-log-prefix {
  color: #94a3b8;
  margin-right: 6px;
}
#${TERMINAL_PANEL_ID} .sd-log-level-success { color: #4ade80; }
#${TERMINAL_PANEL_ID} .sd-log-level-warn { color: #facc15; }
#${TERMINAL_PANEL_ID} .sd-log-level-error { color: #fb7185; }
#${TERMINAL_PANEL_ID} .sd-log-level-info { color: #a5b4fc; }
#${TERMINAL_PANEL_ID} .sd-log-level-normal { color: #dbeafe; }
#${TERMINAL_PANEL_ID} .sd-log-empty {
  color: #64748b;
  font-style: italic;
}
#${TERMINAL_PANEL_ID} .sd-terminal-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}
#${TERMINAL_PANEL_ID} .sd-terminal-actions button {
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 4px 10px;
  background: #fff;
  color: #334155;
  cursor: pointer;
}
@media (max-width: 1200px) {
  #${TERMINAL_PANEL_ID} .sd-terminal-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  #${TERMINAL_PANEL_ID} .sd-terminal-summary { grid-template-columns: 1fr; }
}
`;
    document.head.appendChild(style);
  }

  function ensureTerminalPanel() {
    if (!isTerminalPage()) {
      stopTerminalPolling();
      closeTerminalStreams();
      return;
    }
    const host = document.querySelector(".theme-default-content > div");
    if (!host) return;
    if (!document.getElementById(TERMINAL_PANEL_ID)) {
      ensureTerminalStyle();
      const panel = document.createElement("section");
      panel.id = TERMINAL_PANEL_ID;
      panel.innerHTML = `
<div class="sd-terminal-head">
  <div class="sd-terminal-title">
    <span class="sd-terminal-dot"></span>
    <strong>AI 训练控制台</strong>
    <span class="sd-terminal-title-sub">Workspace</span>
    <span class="sd-terminal-meta" data-terminal-global-status>空闲</span>
  </div>
  <div class="sd-terminal-filters">
    <button class="sd-filter-chip active" data-terminal-filter="all">全部</button>
    <button class="sd-filter-chip" data-terminal-filter="train">训练</button>
    <button class="sd-filter-chip" data-terminal-filter="deploy">部署</button>
    <button class="sd-filter-chip" data-terminal-filter="system">系统</button>
  </div>
</div>
<div class="sd-terminal-body">
  <div class="sd-terminal-cards">
    <div class="sd-card"><div class="sd-card-label">GPU</div><div class="sd-card-value" data-terminal-card="gpu">--</div></div>
    <div class="sd-card"><div class="sd-card-label">显存</div><div class="sd-card-value" data-terminal-card="vram">--</div></div>
    <div class="sd-card"><div class="sd-card-label">Epoch</div><div class="sd-card-value" data-terminal-card="epoch">--</div></div>
    <div class="sd-card"><div class="sd-card-label">训练速度</div><div class="sd-card-value" data-terminal-card="speed">--</div></div>
  </div>
  <div class="sd-terminal-summary">
    <div class="sd-summary-item"><b>当前模型</b><code data-terminal-summary="model">--</code></div>
    <div class="sd-summary-item"><b>训练配置</b><code data-terminal-summary="config">--</code></div>
  </div>
  <div class="sd-terminal-actions">
    <button type="button" data-terminal-export>导出日志</button>
    <button type="button" data-terminal-clear>清空</button>
  </div>
  <div class="sd-terminal-meta" data-terminal-install-meta>部署任务：等待中...</div>
  <div class="sd-terminal-meta" data-terminal-train-meta>训练任务：等待中...</div>
  <div class="sd-terminal-shell">
    <div class="sd-shell-bar"><div class="sd-shell-dots"><span></span><span></span><span></span></div><span class="sd-shell-title">unified-train-console.log</span></div>
    <div class="sd-terminal-log" data-terminal-log="unified"></div>
  </div>
</div>`;
      host.appendChild(panel);
    }
    if (!terminalHintInstallTaskId) {
      const params = new URLSearchParams(location.search || "");
      if (params.get("focus") === "deploy") {
        terminalFilter = "deploy";
      }
      terminalHintInstallTaskId = params.get("task_id") || params.get("source_task") || "";
    }
    bindTerminalPanelEvents();
    renderTerminalLog();
    if (!terminalPollTimer) {
      refreshTerminalPanel();
      terminalPollTimer = setInterval(refreshTerminalPanel, 2000);
    }
  }

  function escapeHtml(text) {
    return String(text)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function classifyLogLevel(line) {
    const raw = (line || "").toLowerCase();
    if (/\[error\]|traceback|exception|failed|fatal/.test(raw)) return "error";
    if (/\[warn\]|warning|retry|timeout|drift/.test(raw)) return "warn";
    if (/\[ready\]|\[done\]|success|passed|ok/.test(raw)) return "success";
    if (/\[task\]|\[phase\]|starting|running|status/.test(raw)) return "info";
    return "normal";
  }

  function updateMetricFromLine(line) {
    const text = line || "";
    const epochMatch = text.match(/epoch(?:s)?\s*[:= ]\s*(\d+)(?:\s*[\/|]\s*(\d+))?/i);
    if (epochMatch) {
      terminalMetricStore.epoch = epochMatch[2] ? `${epochMatch[1]}/${epochMatch[2]}` : epochMatch[1];
    }
    const speedMatch = text.match(/(\d+(?:\.\d+)?)\s*(it\/s|steps?\/s|s\/it)/i);
    if (speedMatch) {
      terminalMetricStore.speed = `${speedMatch[1]} ${speedMatch[2]}`;
    }
  }

  function sourceLabel(source) {
    if (source === "train") return "训练";
    if (source === "deploy") return "部署";
    return "系统";
  }

  function sourceAllowed(source) {
    if (terminalFilter === "all") return true;
    return source === terminalFilter;
  }

  function renderTerminalLog() {
    const box = document.querySelector(`[data-terminal-log="unified"]`);
    if (!box) return;
    const items = (terminalLogStore.items || []).filter((item) => sourceAllowed(item.source));
    if (items.length === 0) {
      box.innerHTML = `<div class="sd-log-empty">暂无日志，等待任务启动...</div>`;
      return;
    }
    const html = items
      .map((item) => {
        const level = classifyLogLevel(item.text);
        return `<div class="sd-log-line sd-log-level-${level}"><span class="sd-log-prefix">[${sourceLabel(item.source)}]</span>${escapeHtml(item.text)}</div>`;
      })
      .join("");
    box.innerHTML = html;
    box.scrollTop = box.scrollHeight;
  }

  function appendTerminalLog(source, text) {
    if (!text) return;
    const lines = String(text).split(/\r?\n/).filter(Boolean);
    lines.forEach((line) => {
      terminalLogStore.items.push({ source, text: line });
      if (source === "train") updateMetricFromLine(line);
    });
    if (terminalLogStore.items.length > 2800) {
      terminalLogStore.items = terminalLogStore.items.slice(-2200);
    }
    renderTerminalLog();
  }

  function setTerminalMeta(kind, text) {
    const el = document.querySelector(
      kind === "install" ? "[data-terminal-install-meta]" : "[data-terminal-train-meta]"
    );
    if (el) el.textContent = text;
  }

  async function fetchJson(url) {
    const r = await fetch(url);
    const j = await r.json();
    return j && j.data ? j.data : {};
  }

  async function fillLogTail(taskId, source) {
    try {
      const data = await fetchJson(`/api/train/log/tail/${encodeURIComponent(taskId)}?limit=160`);
      (data.lines || []).forEach((line) => appendTerminalLog(source, line));
    } catch (_) {
      appendTerminalLog("system", "[warn] 无法读取历史日志");
    }
  }

  async function connectTerminalStream(source, taskId, installAlias) {
    if (!taskId) return;
    if (source === "deploy" && terminalInstallTaskId === taskId && terminalInstallEs) return;
    if (source === "train" && terminalTrainTaskId === taskId && terminalTrainEs) return;

    const streamUrl = installAlias
      ? `/api/plugins/anima-lora/install/log/stream/${encodeURIComponent(taskId)}`
      : `/api/train/log/stream/${encodeURIComponent(taskId)}`;
    await fillLogTail(taskId, source);

    if (!window.EventSource) {
      appendTerminalLog("system", "[warn] 当前浏览器不支持实时日志流");
      return;
    }
    if (source === "deploy" && terminalInstallEs) terminalInstallEs.close();
    if (source === "train" && terminalTrainEs) terminalTrainEs.close();

    const es = new EventSource(streamUrl);
    es.onmessage = function (e) {
      try {
        const payload = JSON.parse(e.data);
        if (payload.text) appendTerminalLog(source, payload.text);
        if (payload.done) appendTerminalLog("system", `[done] ${source === "deploy" ? "部署" : "训练"}日志流结束`);
      } catch (_) {
        appendTerminalLog(source, e.data);
      }
    };
    es.onerror = function () {
      appendTerminalLog("system", `[warn] ${source === "deploy" ? "部署" : "训练"}日志流断开`);
      es.close();
      if (source === "deploy") terminalInstallEs = null;
      if (source === "train") terminalTrainEs = null;
    };

    if (source === "deploy") {
      terminalInstallTaskId = taskId;
      terminalInstallEs = es;
    } else {
      terminalTrainTaskId = taskId;
      terminalTrainEs = es;
    }
  }

  function findLatestTask(tasks, predicate) {
    const list = Array.isArray(tasks) ? tasks.slice().reverse() : [];
    return list.find(predicate) || null;
  }

  function getDeep(obj, path, fallback) {
    let cur = obj;
    for (const key of path) {
      if (!cur || typeof cur !== "object" || !(key in cur)) return fallback;
      cur = cur[key];
    }
    return cur == null ? fallback : cur;
  }

  function setCard(name, value) {
    const el = document.querySelector(`[data-terminal-card="${name}"]`);
    if (el) el.textContent = value || "--";
  }

  function setSummary(name, value) {
    const el = document.querySelector(`[data-terminal-summary="${name}"]`);
    if (el) el.textContent = value || "--";
  }

  function updateTerminalOverview(plugin, latestTrain) {
    const gpuRaw = getDeep(plugin, ["facts", "audit", "facts", "anima", "gpu"], "--");
    const gpu = String(gpuRaw || "--");
    const vramMatch = gpu.match(/\(([^)]+)\)/);
    const vram = vramMatch ? vramMatch[1] : "--";
    setCard("gpu", gpu.replace(/\s*\([^)]*\)\s*$/, "") || "--");
    setCard("vram", vram);
    setCard("epoch", terminalMetricStore.epoch || "--");
    setCard("speed", terminalMetricStore.speed || "--");

    const meta = (latestTrain && latestTrain.metadata) || {};
    const model =
      meta.pretrained_model_name_or_path ||
      meta.model_path ||
      getDeep(plugin, ["facts", "plan", "source_root"], "--");
    const config = meta.config_path || meta.output_dir || "--";
    setSummary("model", model || "--");
    setSummary("config", config || "--");
  }

  function exportTerminalLog() {
    const lines = (terminalLogStore.items || [])
      .filter((item) => sourceAllowed(item.source))
      .map((item) => `[${sourceLabel(item.source)}] ${item.text}`);
    const content = lines.join("\n");
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    a.href = URL.createObjectURL(blob);
    a.download = `terminal-${terminalFilter}-${stamp}.log`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  async function refreshTerminalPanel() {
    if (!isTerminalPage()) return;
    try {
      const plugin = await fetchJson("/api/plugins/anima-lora/status");
      const tasksData = await fetchJson("/api/tasks");
      const tasks = tasksData.tasks || [];

      const installTask = findLatestTask(
        tasks,
        (t) => t && t.metadata && t.metadata.kind === "anima_fast_install"
      );
      const runningTrain = findLatestTask(
        tasks,
        (t) =>
          t &&
          (!t.metadata || t.metadata.kind !== "anima_fast_install") &&
          t.status === "RUNNING"
      );
      const latestTrain = runningTrain || findLatestTask(
        tasks,
        (t) => t && (!t.metadata || t.metadata.kind !== "anima_fast_install")
      );

      const global = document.querySelector("[data-terminal-global-status]");
      if (global) {
        const g = installTask && installTask.status === "RUNNING"
          ? "环境部署中"
          : latestTrain && latestTrain.status === "RUNNING"
          ? "训练进行中"
          : plugin.state === "broken"
          ? "插件需修复"
          : "空闲";
        global.textContent = g;
      }

      const installTaskId =
        (installTask && installTask.id) ||
        (plugin && plugin.facts && plugin.facts.task_id) ||
        terminalHintInstallTaskId;
      if (installTaskId) {
        const statusText = installTask ? installTask.status : plugin.state || "unknown";
        setTerminalMeta("install", `部署任务：task=${installTaskId} · ${statusText}`);
        connectTerminalStream("deploy", installTaskId, true);
      } else {
        setTerminalMeta("install", `部署任务：插件状态 ${plugin.state || "unknown"}`);
      }

      if (latestTrain) {
        setTerminalMeta("train", `训练任务：task=${latestTrain.id} · ${latestTrain.status}`);
        connectTerminalStream("train", latestTrain.id, false);
      } else {
        setTerminalMeta("train", "训练任务：等待中...");
      }
      updateTerminalOverview(plugin, latestTrain);
    } catch (err) {
      appendTerminalLog("system", `[error] 终端状态刷新失败: ${err}`);
    }
  }

  function bindTerminalPanelEvents() {
    const panel = document.getElementById(TERMINAL_PANEL_ID);
    if (!panel || panel.dataset.bound === "1") return;
    panel.dataset.bound = "1";
    panel.addEventListener("click", function (ev) {
      const chip = ev.target.closest("[data-terminal-filter]");
      if (chip) {
        terminalFilter = chip.getAttribute("data-terminal-filter") || "all";
        panel.querySelectorAll("[data-terminal-filter]").forEach((b) => {
          b.classList.toggle("active", b === chip);
        });
        renderTerminalLog();
        return;
      }
      const clearBtn = ev.target.closest("[data-terminal-clear]");
      if (clearBtn) {
        if (terminalFilter === "all") {
          terminalLogStore.items = [];
        } else {
          terminalLogStore.items = terminalLogStore.items.filter((item) => item.source !== terminalFilter);
        }
        renderTerminalLog();
        return;
      }
      const exportBtn = ev.target.closest("[data-terminal-export]");
      if (exportBtn) {
        exportTerminalLog();
      }
    });
  }

  function applyNavLocale() {
    const english = detectEnglishUI();
    document.documentElement.dataset.sdUiLocale = english ? "en-US" : "zh-CN";

    const map = english ? ZH_TO_EN : EN_TO_ZH;
    ensureSidebarTerminalLink();
    ensureTagEditorLinks();
    const sidebar = document.querySelector(".sidebar .sidebar-items");
    if (sidebar) replaceInElement(sidebar, map);

    const sidebarBottom = document.querySelector(".sidebar-bottom");
    if (sidebarBottom) replaceInElement(sidebarBottom, map);

    const hub = document.querySelector(".sd-home-hub");
    if (hub) replaceInElement(hub, map);

    const main = document.querySelector(".right-container .theme-default-content main");
    if (main) replaceInElement(main, map);

    const schemaForm = document.querySelector("section.schema-container");
    if (schemaForm) replaceInElement(schemaForm, map);

    const rightHeader = document.querySelector(".right-container section > header");
    if (rightHeader) replaceInElement(rightHeader, map);

    const buttons = document.querySelector(".right-container .el-row");
    if (buttons) replaceInElement(buttons.closest(".right-container") || buttons, map);

    const tagline = document.querySelector(".sd-anima-finetune-tagline");
    if (tagline && english) {
      tagline.textContent = "anima-finetune — anything is possible";
    } else if (tagline && !english) {
      tagline.textContent = "anima-finetune ，一切皆有可能";
    }

    ensureTerminalPanel();
  }

  function hookLanguageToggle() {
    const bottom = document.querySelector(".sidebar-bottom");
    if (!bottom || bottom.dataset.sdNavI18nHooked) return;
    bottom.dataset.sdNavI18nHooked = "1";
    bottom.addEventListener(
      "click",
      (ev) => {
        const btn = ev.target.closest("button");
        if (!btn) return;
        const row = btn.closest("li.appearance");
        if (!row || !/language/i.test(row.textContent || "")) return;
        const next = detectEnglishUI() ? "zh-CN" : "en-US";
        localStorage.setItem(STORAGE_KEY, next);
        setTimeout(applyNavLocale, 80);
        setTimeout(applyNavLocale, 400);
      },
      true
    );
  }

  let scheduled = null;
  function scheduleApply() {
    if (scheduled) clearTimeout(scheduled);
    scheduled = setTimeout(() => {
      scheduled = null;
      ensureAnimaLokrConfigGuard();
      applyNavLocale();
      hookLanguageToggle();
      ensureTerminalPanel();
    }, 60);
  }

  function boot() {
    migrateLegacyLocale();
    ensureAnimaLokrConfigGuard();
    applyNavLocale();
    hookLanguageToggle();
    ensureTerminalPanel();

    const root = document.querySelector("#app");
    if (root) {
      new MutationObserver(scheduleApply).observe(root, {
        childList: true,
        subtree: true,
      });
    }
    window.addEventListener("hashchange", scheduleApply);
    window.addEventListener("popstate", scheduleApply);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
  window.addEventListener("beforeunload", function () {
    stopTerminalPolling();
    closeTerminalStreams();
  });
})();
