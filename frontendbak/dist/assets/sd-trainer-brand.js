/**
 * Version chip next to the "Next Trainer" sidebar title (reads /api/version).
 */
(function () {
  const VERSION_URL = "/api/version";
  const CHIP_ID = "sd-brand-version-chip";
  const BRAND_TITLE = "Next Trainer";
  const GAP_PX = 6;
  const OFFSET_Y_PX = 3;

  function versionFromScriptTag() {
    const el = document.querySelector('script[src*="sd-trainer-brand.js"]');
    if (!el) return null;
    try {
      const v = new URL(el.src, window.location.origin).searchParams.get("v");
      return v ? String(v).trim() : null;
    } catch (e) {
      return null;
    }
  }

  async function fetchVersion() {
    try {
      const res = await fetch(VERSION_URL);
      const json = await res.json();
      if (json && json.status === "success" && json.data && json.data.version) {
        return String(json.data.version).trim();
      }
    } catch (e) {
      /* backend offline */
    }
    return versionFromScriptTag();
  }

  function findBrandLink() {
    const sidebar = document.querySelector(".sidebar .sidebar-items");
    if (!sidebar) return null;
    return (
      sidebar.querySelector("li:first-child > a.sidebar-item.sidebar-heading[href='/']") ||
      sidebar.querySelector('a.sidebar-item.sidebar-heading[aria-label="Next Trainer"]')
    );
  }

  function measureBrandTitleRect(link) {
    const walker = document.createTreeWalker(link, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const raw = node.textContent || "";
      const idx = raw.indexOf(BRAND_TITLE);
      if (idx !== -1) {
        const range = document.createRange();
        range.setStart(node, idx);
        range.setEnd(node, idx + BRAND_TITLE.length);
        const r = range.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) return r;
      }
    }
    return link.getBoundingClientRect();
  }

  function positionChip() {
    const chip = document.getElementById(CHIP_ID);
    const link = findBrandLink();
    if (!chip || !link) {
      if (chip) chip.style.visibility = "hidden";
      return false;
    }

    const linkRect = link.getBoundingClientRect();
    const titleRect = measureBrandTitleRect(link);
    if (linkRect.width <= 0 || linkRect.height <= 0) {
      chip.style.visibility = "hidden";
      return false;
    }

    chip.style.visibility = "visible";
    const anchor = titleRect.height > 0 ? titleRect : linkRect;
    chip.style.top =
      Math.round(anchor.top + (anchor.height - chip.offsetHeight) / 2 + OFFSET_Y_PX) + "px";
    chip.style.left = Math.round(titleRect.right + GAP_PX) + "px";
    chip.style.right = "auto";
    return true;
  }

  function ensureChip(version) {
    if (!version) return;
    document.documentElement.dataset.sdTrainerVersion = version;

    let chip = document.getElementById(CHIP_ID);
    if (!chip) {
      chip = document.createElement("div");
      chip.id = CHIP_ID;
      chip.className = "sd-brand-version-chip";
      chip.setAttribute("title", "Next Trainer / SD-Trainer 版本号");
      document.body.appendChild(chip);
    }
    chip.textContent = "v" + version;
    positionChip();
  }

  let resizeTimer = null;
  function scheduleReposition() {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(positionChip, 80);
  }

  function loadAnimaFastInstall() {
    if (window.__ANIMA_FAST_INSTALL_GUARD__) return;
    const existing = document.querySelector('script[src*="anima-fast-install.js"]');
    if (existing) return;
    const version = versionFromScriptTag() || "2.7.0";
    const script = document.createElement("script");
    script.src = "/assets/anima-fast-install.js?v=" + encodeURIComponent(version);
    script.defer = true;
    document.head.appendChild(script);
  }

  const GUIDE_PAGE_HASHES = ["#新手上路", "#从秋叶版迁移", "#anima-fast-lora"];

  function hashToGuideIndex() {
    const hash = location.hash || "#新手上路";
    const i = GUIDE_PAGE_HASHES.indexOf(hash);
    return i >= 0 ? i : 0;
  }

  function setupGuidePagerRoot(root) {
    if (!root || root.dataset.guidePagerReady === "1") return;
    root.dataset.guidePagerReady = "1";

    const pages = Array.from(root.querySelectorAll("[data-guide-page]"));
    if (!pages.length) return;

    const prevBtn = root.querySelector("[data-guide-prev]");
    const nextBtn = root.querySelector("[data-guide-next]");
    const countEl = root.querySelector("[data-guide-count]");
    let index = hashToGuideIndex();

    function setPage(i, opts) {
      index = Math.max(0, Math.min(pages.length - 1, i));
      pages.forEach(function (p, j) {
        p.classList.toggle("is-active", j === index);
        p.hidden = j !== index;
      });
      if (prevBtn) prevBtn.disabled = index === 0;
      if (nextBtn) nextBtn.disabled = index === pages.length - 1;
      if (countEl) countEl.textContent = index + 1 + " / " + pages.length;
      root.dataset.guideCurrentPage = String(index);
      const hash = GUIDE_PAGE_HASHES[index];
      if (!opts || !opts.skipHash) {
        const url = location.pathname + location.search + hash;
        if (location.pathname + location.search + location.hash !== url) {
          history.replaceState(null, "", url);
        }
      }
      const viewport = root.querySelector(".sd-guide-pager__viewport");
      if (viewport) viewport.scrollTop = 0;
      const main = document.querySelector("main.page");
      if (main) main.scrollTop = 0;
    }

    root._guideSetPage = setPage;
    setPage(index, { skipHash: true });
  }

  function scanGuidePagers() {
    if (!/^\/help\/guide(\.html|\.md)?$/i.test(location.pathname)) return;
    document.querySelectorAll("[data-guide-pager]").forEach(setupGuidePagerRoot);
  }

  function syncGuidePagerFromHash() {
    if (!/^\/help\/guide(\.html|\.md)?$/i.test(location.pathname)) return;
    const idx = hashToGuideIndex();
    document.querySelectorAll("[data-guide-pager]").forEach(function (root) {
      if (root.dataset.guidePagerReady === "1" && typeof root._guideSetPage === "function") {
        root._guideSetPage(idx, { skipHash: true });
      }
    });
  }

  function onGuidePagerClick(ev) {
    const prev = ev.target && ev.target.closest && ev.target.closest("[data-guide-prev]");
    const next = ev.target && ev.target.closest && ev.target.closest("[data-guide-next]");
    if (!prev && !next) return;
    const root = (prev || next).closest("[data-guide-pager]");
    if (!root) return;
    ev.preventDefault();
    if (root.dataset.guidePagerReady !== "1") setupGuidePagerRoot(root);
    const idx = parseInt(root.dataset.guideCurrentPage || "0", 10);
    const total = root.querySelectorAll("[data-guide-page]").length;
    if (prev && idx > 0 && typeof root._guideSetPage === "function") root._guideSetPage(idx - 1);
    if (next && idx < total - 1 && typeof root._guideSetPage === "function") root._guideSetPage(idx + 1);
  }

  function watchGuidePagerMount() {
    if (window.__sdGuidePagerWatcher__) return;
    window.__sdGuidePagerWatcher__ = true;
    const obs = new MutationObserver(function () {
      scanGuidePagers();
    });
    if (document.body) {
      obs.observe(document.body, { childList: true, subtree: true });
    }
  }

  function scheduleGuidePager() {
    scanGuidePagers();
    let left = 60;
    const timer = setInterval(function () {
      scanGuidePagers();
      if (--left <= 0) clearInterval(timer);
    }, 150);
  }

  document.addEventListener("click", onGuidePagerClick);

  document.addEventListener("click", function (ev) {
    const link = ev.target && ev.target.closest && ev.target.closest("[data-guide-fast-link]");
    if (!link) return;
    ev.preventDefault();
    window.location.assign("/help/guide.html#anima-fast-lora");
  });

  async function boot() {
    const version = (await fetchVersion()) || versionFromScriptTag();
    if (version) ensureChip(version);
    setupMobileNav();
    loadAnimaFastInstall();
    watchGuidePagerMount();
    scheduleGuidePager();
    window.addEventListener("hashchange", function () {
      scanGuidePagers();
      syncGuidePagerFromHash();
    });

    let tries = 0;
    const retry = setInterval(function () {
      positionChip();
      if (++tries >= 30) clearInterval(retry);
    }, 200);

    window.addEventListener("resize", scheduleReposition);
    window.addEventListener("scroll", scheduleReposition, true);
  }

  function setupMobileNav() {
    const root = document.querySelector(".theme-container.no-navbar");
    if (!root || document.querySelector(".sd-mobile-nav-toggle")) return;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sd-mobile-nav-toggle";
    btn.setAttribute("aria-label", "打开导航菜单");
    btn.setAttribute("aria-expanded", "false");
    btn.textContent = "\u2630";
    document.body.appendChild(btn);

    const mask = root.querySelector(".sidebar-mask");

    function closeNav() {
      root.classList.remove("sidebar-open");
      btn.setAttribute("aria-expanded", "false");
      btn.setAttribute("aria-label", "打开导航菜单");
    }

    btn.addEventListener("click", function () {
      if (root.classList.contains("sidebar-open")) {
        closeNav();
        return;
      }
      root.classList.add("sidebar-open");
      btn.setAttribute("aria-expanded", "true");
      btn.setAttribute("aria-label", "关闭导航菜单");
    });

    if (mask) {
      mask.addEventListener("click", closeNav);
    }

    window.addEventListener("resize", function () {
      if (window.innerWidth > 959) {
        closeNav();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
