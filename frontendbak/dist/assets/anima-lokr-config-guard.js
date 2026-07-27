(function () {
  "use strict";

  const LYCO_MODULE_RE = /\bnetwork_module\s*=\s*["']lycoris\.kohya["']/i;
  const NETWORK_ARGS_START_RE =
    /^[ \t]*network_args\s*=\s*\[[ \t]*(?:#.*)?$/i;
  const NETWORK_ARGS_END_RE = /^[ \t]*\][ \t]*(?:#.*)?$/;
  const INVALID_ARG_LINE_RE =
    /^[ \t]*["'][^"'=\r\n]+\s*=\s*(?:undefined|null|nan)["'][ \t]*,?[ \t]*$/i;
  const ANIMA_STANDARD_PATH_RE = /^\/lora\/sd3(?:\.(?:html|md))?\/?$/i;

  function isAnimaStandardPage() {
    return ANIMA_STANDARD_PATH_RE.test(location.pathname || "");
  }

  function sanitizeLycorisToml(value) {
    if (typeof value !== "string" || !LYCO_MODULE_RE.test(value)) {
      return value;
    }

    const newline = value.includes("\r\n") ? "\r\n" : "\n";
    const lines = value.split(/\r?\n/);
    const cleaned = [];
    let inNetworkArgs = false;
    let changed = false;

    lines.forEach(function (line) {
      if (!inNetworkArgs) {
        cleaned.push(line);
        if (NETWORK_ARGS_START_RE.test(line)) {
          inNetworkArgs = true;
        }
        return;
      }

      if (NETWORK_ARGS_END_RE.test(line)) {
        inNetworkArgs = false;
        cleaned.push(line);
        return;
      }

      if (INVALID_ARG_LINE_RE.test(line)) {
        changed = true;
        return;
      }

      cleaned.push(line);
    });

    return changed ? cleaned.join(newline) : value;
  }

  window.mikazukiSanitizeLycorisTomlText = sanitizeLycorisToml;
  window.mikazukiAnimaLokrGuardLoaded = true;

  // The vendored layout creates the TOML Blob synchronously in its download
  // click handler. Wrap Blob only for that event turn, then restore it. Using
  // the native prototype preserves instanceof checks while the wrapper is live.
  const NativeBlob = window.Blob;
  let blobRestoreTimer = null;

  function installDownloadBlobForCurrentClick() {
    if (typeof NativeBlob !== "function" || window.Blob !== NativeBlob) {
      return;
    }

    function ScopedConfigBlob(parts, options) {
      const safeParts = Array.isArray(parts)
        ? parts.map(function (part) {
            return typeof part === "string" ? sanitizeLycorisToml(part) : part;
          })
        : parts;
      return new NativeBlob(safeParts, options);
    }

    Object.setPrototypeOf(ScopedConfigBlob, NativeBlob);
    ScopedConfigBlob.prototype = NativeBlob.prototype;
    window.Blob = ScopedConfigBlob;

    clearTimeout(blobRestoreTimer);
    blobRestoreTimer = setTimeout(function () {
      if (window.Blob === ScopedConfigBlob) {
        window.Blob = NativeBlob;
      }
    }, 0);
  }

  function isConfigDownloadButton(target) {
    const button = target && target.closest ? target.closest("button") : null;
    if (!button || !button.closest(".right-container")) {
      return false;
    }
    const text = (button.textContent || "").replace(/\s+/g, " ").trim();
    return text === "下载配置文件" || /^download config$/i.test(text);
  }

  function sanitizePreviewTextNode(node) {
    if (
      !isAnimaStandardPage() ||
      node.nodeType !== Node.TEXT_NODE ||
      !node.parentElement ||
      !node.parentElement.closest(".params-section")
    ) {
      return;
    }
    const cleaned = sanitizeLycorisToml(node.nodeValue);
    if (cleaned !== node.nodeValue) {
      node.nodeValue = cleaned;
    }
  }

  function sanitizePreviewTree(root) {
    if (!root) {
      return;
    }
    if (root.nodeType === Node.TEXT_NODE) {
      sanitizePreviewTextNode(root);
      return;
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      sanitizePreviewTextNode(node);
    }
  }

  function sanitizeCurrentPreview() {
    if (!isAnimaStandardPage()) {
      return;
    }
    const preview = document.querySelector(".params-section");
    sanitizePreviewTree(preview);
  }

  function installPreviewGuard() {
    sanitizeCurrentPreview();
    const root = document.querySelector("#app");
    if (!root) {
      return;
    }
    new MutationObserver(function (mutations) {
      if (!isAnimaStandardPage()) {
        return;
      }
      mutations.forEach(function (mutation) {
        if (mutation.type === "characterData") {
          sanitizePreviewTextNode(mutation.target);
          return;
        }
        mutation.addedNodes.forEach(sanitizePreviewTree);
      });
    }).observe(root, {
      childList: true,
      characterData: true,
      subtree: true,
    });
  }

  document.addEventListener(
    "click",
    function (event) {
      if (isAnimaStandardPage() && isConfigDownloadButton(event.target)) {
        installDownloadBlobForCurrentClick();
      }
    },
    true
  );

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", installPreviewGuard, { once: true });
  } else {
    installPreviewGuard();
  }
  window.addEventListener("popstate", function () {
    setTimeout(sanitizeCurrentPreview, 0);
  });
  window.addEventListener("hashchange", function () {
    setTimeout(sanitizeCurrentPreview, 0);
  });
})();
