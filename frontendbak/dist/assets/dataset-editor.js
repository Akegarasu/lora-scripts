(function () {
  function initDatasetEditor() {
  const root = document.getElementById("sd-native-editor-entry") || document.querySelector(".de-shell");
  if (!root || root.dataset.sdDatasetEditorBound === "true") return;
  root.dataset.sdDatasetEditorBound = "true";

  const QUICK_TAGS_KEY = "sd-trainer.dataset-editor.quick-tags";
  const API_HISTORY = "/api/dataset-editor/history";
  const API_UNDO = "/api/dataset-editor/undo";
  const API_REDO = "/api/dataset-editor/redo";
  const TAG_COLLAPSED_LIMIT = 18;
  const TAG_SEARCH_LIMIT = 80;
  const TAG_EXPANDED_LIMIT = 240;
  const DEFAULT_GALLERY_PAGE_SIZE = "auto";
  const GALLERY_PAGE_SIZE = 20;
  const GALLERY_PAGE_SIZE_KEY = "sd-trainer.dataset-editor.gallery-page-size";
  const THUMBNAIL_FIT_KEY = "sd-trainer.dataset-editor.thumbnail-fit";
  const DEFAULT_QUICK_TAGS = ["masterpiece", "best quality", "1girl", "solo", "smile", "looking at viewer"];

  const state = {
    root: "",
    items: [],
    filtered: [],
    selected: -1,
    selectedPaths: new Set(),
    selectionMode: "manual",
    galleryPage: 0,
    galleryPageSize: loadGalleryPageSize(),
    autoGalleryPageSize: GALLERY_PAGE_SIZE,
    thumbnailFit: localStorage.getItem(THUMBNAIL_FIT_KEY) || "contain",
    dirty: false,
    tags: [],
    tagExpanded: false,
    categories: [],
    category: "",
    changes: [],
    canUndo: false,
    canRedo: false,
    quickTags: loadQuickTags(),
  };

  const el = {
    path: document.getElementById("dataset-path"),
    pick: document.getElementById("pick-folder"),
    scan: document.getElementById("scan-dataset"),
    status: document.getElementById("status"),
    search: document.getElementById("search-tags"),
    category: document.getElementById("category-filter"),
    include: document.getElementById("include-tags"),
    exclude: document.getElementById("exclude-tags"),
    datasetCount: document.getElementById("dataset-count"),
    filteredCount: document.getElementById("filtered-count"),
    tagList: document.getElementById("tag-list"),
    tagToggle: document.getElementById("tag-toggle"),
    sideTabs: Array.from(document.querySelectorAll("[data-side-tab]")),
    sidePanels: {
      clean: document.getElementById("side-panel-clean"),
      filter: document.getElementById("side-panel-filter"),
      quick: document.getElementById("side-panel-quick"),
      batch: document.getElementById("side-panel-batch"),
      tagger: document.getElementById("side-panel-tagger"),
    },
    quickTags: document.getElementById("quick-tags"),
    quickTagInput: document.getElementById("quick-tag-input"),
    quickTagAdd: document.getElementById("quick-tag-add"),
    changeList: document.getElementById("change-list"),
    gallery: document.getElementById("gallery"),
    galleryFirstPage: document.getElementById("gallery-first-page"),
    galleryPrevPage: document.getElementById("gallery-prev-page"),
    galleryPageInput: document.getElementById("gallery-page-input"),
    galleryPageSize: document.getElementById("gallery-page-size"),
    galleryNextPage: document.getElementById("gallery-next-page"),
    galleryLastPage: document.getElementById("gallery-last-page"),
    galleryPageInfo: document.getElementById("gallery-page-info"),
    selectionSummary: document.getElementById("selection-summary"),
    selectPage: document.getElementById("select-page"),
    selectFiltered: document.getElementById("select-filtered"),
    selectAll: document.getElementById("select-all"),
    clearSelection: document.getElementById("clear-selection"),
    thumbnailFit: document.getElementById("thumbnail-fit"),
    preview: document.getElementById("preview"),
    selectedName: document.getElementById("selected-name"),
    dirtyFlag: document.getElementById("dirty-flag"),
    caption: document.getElementById("caption"),
    save: document.getElementById("save-caption"),
    undo: document.getElementById("undo-edit"),
    redo: document.getElementById("redo-edit"),
    prev: document.getElementById("prev-image"),
    next: document.getElementById("next-image"),
    append: document.getElementById("append-tags"),
    remove: document.getElementById("remove-tags"),
    replaceFrom: document.getElementById("replace-from"),
    replaceTo: document.getElementById("replace-to"),
    sort: document.getElementById("sort-tags"),
    batch: document.getElementById("apply-batch"),
    taggerTrigger: document.getElementById("tagger-trigger-tags"),
    taggerTriggerApply: document.getElementById("apply-tagger-trigger"),
    cleanCaption: document.getElementById("clean-caption"),
    cleanUnderscore: document.getElementById("clean-underscore"),
    cleanEscape: document.getElementById("clean-escape"),
    cleanSort: document.getElementById("clean-sort"),
    cleanup: document.getElementById("apply-cleanup"),
  };

  function loadQuickTags() {
    try {
      const saved = JSON.parse(localStorage.getItem(QUICK_TAGS_KEY) || "[]");
      return normalizeTagList([...saved, ...DEFAULT_QUICK_TAGS]).slice(0, 24);
    } catch (_err) {
      return DEFAULT_QUICK_TAGS;
    }
  }

  function loadGalleryPageSize() {
    const stored = localStorage.getItem(GALLERY_PAGE_SIZE_KEY);
    if (!stored || stored === "auto") return DEFAULT_GALLERY_PAGE_SIZE;
    const value = Number(stored);
    return [12, 15, 20, 24, 30, 48].includes(value) ? value : DEFAULT_GALLERY_PAGE_SIZE;
  }

  function effectiveGalleryPageSize() {
    return state.galleryPageSize === "auto" ? state.autoGalleryPageSize : Number(state.galleryPageSize);
  }

  function updateAutoGalleryPageSize() {
    const width = el.gallery?.clientWidth || 0;
    const height = el.gallery?.clientHeight || 0;
    const columns = Math.max(1, Math.floor(width / 230));
    const rows = Math.max(1, Math.floor(height / 236));
    state.autoGalleryPageSize = Math.min(60, Math.max(12, columns * rows));
  }

  function saveQuickTags() {
    localStorage.setItem(QUICK_TAGS_KEY, JSON.stringify(state.quickTags.slice(0, 24)));
  }

  function setStatus(text, isError) {
    el.status.textContent = text;
    el.status.style.color = isError ? "#b42318" : "";
  }

  function normalizeTagList(tags) {
    const seen = new Set();
    return tags
      .map((tag) => String(tag || "").trim())
      .filter((tag) => {
        const key = tag.toLowerCase();
        if (!tag || seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  }

  function splitTags(value) {
    return normalizeTagList(String(value || "").split(","));
  }

  async function api(url, options) {
    const res = await fetch(url, options);
    const json = await res.json().catch(() => null);
    if (!res.ok || !json || json.status !== "success") {
      const message = json?.message || json?.detail || res.statusText || "请求失败";
      throw new Error(message);
    }
    return json.data || {};
  }

  function currentItem() {
    if (state.selected < 0) return null;
    return state.filtered[state.selected] || null;
  }

  function itemPath(item) {
    return item?.relative_path || "";
  }

  function currentPageItems() {
    const pageSize = effectiveGalleryPageSize();
    const start = state.galleryPage * pageSize;
    return state.filtered.slice(start, start + pageSize);
  }

  function selectedBatchItems() {
    if (!state.selectedPaths.size) return state.filtered;
    const selected = new Set(state.selectedPaths);
    return state.items.filter((item) => selected.has(itemPath(item)));
  }

  function pruneSelection() {
    const existing = new Set(state.items.map((item) => itemPath(item)));
    state.selectedPaths.forEach((path) => {
      if (!existing.has(path)) state.selectedPaths.delete(path);
    });
  }

  function toggleItemSelection(item) {
    const path = itemPath(item);
    if (!path) return;
    if (state.selectedPaths.has(path)) {
      state.selectedPaths.delete(path);
    } else {
      state.selectedPaths.add(path);
    }
    state.selectionMode = "manual";
    render();
  }

  function selectPageItems() {
    currentPageItems().forEach((item) => state.selectedPaths.add(itemPath(item)));
    state.selectionMode = "page";
    render();
  }

  function selectFilteredItems() {
    state.filtered.forEach((item) => state.selectedPaths.add(itemPath(item)));
    state.selectionMode = "filtered";
    render();
  }

  function selectAllItems() {
    state.items.forEach((item) => state.selectedPaths.add(itemPath(item)));
    state.selectionMode = "all";
    render();
  }

  function clearSelection() {
    state.selectedPaths.clear();
    state.selectionMode = "manual";
    render();
  }

  function confirmDirty() {
    if (!state.dirty) return true;
    return window.confirm("当前 caption 尚未保存，确定切换图片吗？");
  }

  function applyFilters() {
    const query = el.search.value.trim().toLowerCase();
    const include = splitTags(el.include.value).map((tag) => tag.toLowerCase());
    const exclude = splitTags(el.exclude.value).map((tag) => tag.toLowerCase());
    state.category = el.category.value;
    state.filtered = state.items.filter((item) => {
      const tags = (item.tags || []).map((tag) => tag.toLowerCase());
      const caption = String(item.caption || "").toLowerCase();
      if (state.category && item.category !== state.category) return false;
      if (query && !caption.includes(query) && !tags.some((tag) => tag.includes(query))) return false;
      if (include.length && !include.every((tag) => tags.includes(tag))) return false;
      if (exclude.length && exclude.some((tag) => tags.includes(tag))) return false;
      return true;
    });
    pruneSelection();
    if (state.selected >= state.filtered.length) state.selected = state.filtered.length ? 0 : -1;
    const maxPage = galleryPageCount() - 1;
    if (state.galleryPage > maxPage) state.galleryPage = Math.max(0, maxPage);
    if (state.selected >= 0) state.galleryPage = pageForIndex(state.selected);
    render();
  }

  function renderCategories() {
    const current = state.category;
    el.category.innerHTML = "";
    const all = document.createElement("option");
    all.value = "";
    all.textContent = "全部";
    el.category.appendChild(all);
    state.categories.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.value || "";
      option.textContent = `${item.name || "根目录"} ${item.count || 0}`;
      el.category.appendChild(option);
    });
    el.category.value = state.categories.some((item) => item.value === current) ? current : "";
    state.category = el.category.value;
  }

  function renderTags() {
    const query = el.search.value.trim().toLowerCase();
    const matched = state.tags.filter((item) => !query || item.tag.toLowerCase().includes(query));
    const limit = query ? TAG_SEARCH_LIMIT : state.tagExpanded ? TAG_EXPANDED_LIMIT : TAG_COLLAPSED_LIMIT;
    const tags = matched.slice(0, limit);
    el.tagList.innerHTML = "";
    el.tagList.classList.toggle("is-expanded", state.tagExpanded || !!query);
    tags.forEach((item) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "de-tag";
      chip.textContent = `${item.tag} ${item.count}`;
      chip.title = item.tag;
      chip.addEventListener("click", () => {
        el.include.value = item.tag;
        applyFilters();
      });
      el.tagList.appendChild(chip);
    });
    const hidden = Math.max(0, matched.length - tags.length);
    el.tagToggle.hidden = matched.length <= TAG_COLLAPSED_LIMIT && !state.tagExpanded;
    el.tagToggle.textContent = state.tagExpanded
      ? "收起标签"
      : hidden
      ? `显示更多标签（还有 ${hidden} 个）`
      : "显示更多标签";
  }

  function renderQuickTags() {
    const frequent = state.tags.map((item) => item.tag).slice(0, 18);
    const tags = normalizeTagList([...state.quickTags, ...frequent]).slice(0, 30);
    el.quickTags.innerHTML = "";
    tags.forEach((tag) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "de-tag de-quick-tag";
      chip.textContent = tag;
      chip.title = `添加 ${tag}`;
      chip.addEventListener("click", () => appendTagToCaption(tag));
      el.quickTags.appendChild(chip);
    });
  }

  function renderHistory() {
    el.changeList.innerHTML = "";
    if (!state.root) {
      el.changeList.innerHTML = '<div class="de-empty">扫描数据集后显示本次会话的改动。</div>';
      return;
    }
    if (!state.changes.length) {
      el.changeList.innerHTML = '<div class="de-empty">暂无已保存改动。</div>';
      return;
    }
    state.changes.forEach((change) => {
      const box = document.createElement("div");
      box.className = "de-change";
      const title = document.createElement("strong");
      title.textContent = `${change.label || "编辑"} · ${change.count || 0} 项`;
      box.appendChild(title);
      (change.items || []).slice(0, 4).forEach((item) => {
        const row = document.createElement("div");
        row.className = "de-change-item";
        row.title = item.image;
        row.textContent = item.image;
        box.appendChild(row);
      });
      if ((change.items || []).length > 4) {
        const more = document.createElement("div");
        more.className = "de-change-item";
        more.textContent = `还有 ${(change.items || []).length - 4} 项`;
        box.appendChild(more);
      }
      el.changeList.appendChild(box);
    });
  }

  function renderGallery() {
    const selected = currentItem();
    const pageSize = effectiveGalleryPageSize();
    const start = state.galleryPage * pageSize;
    const pageItems = currentPageItems();
    el.gallery.innerHTML = "";
    el.gallery.classList.toggle("is-cover", state.thumbnailFit === "cover");
    if (!pageItems.length) {
      const empty = document.createElement("div");
      empty.className = "de-gallery-empty";
      empty.innerHTML = state.items.length
        ? "<strong>没有匹配的图片</strong><span>调整左侧范围或筛选条件后继续。</span>"
        : "<strong>未加载数据集</strong><span>从左侧选择 LoRA 训练图片目录后开始编辑。</span>";
      el.gallery.appendChild(empty);
    }
    pageItems.forEach((item, pageIndex) => {
      const index = start + pageIndex;
      const path = itemPath(item);
      const isBulkSelected = state.selectedPaths.has(path);
      const card = document.createElement("button");
      card.type = "button";
      card.className = "de-card";
      card.setAttribute("aria-selected", item === selected ? "true" : "false");
      card.dataset.bulkSelected = isBulkSelected ? "true" : "false";
      card.innerHTML = "<span class=\"de-card-check\" aria-hidden=\"true\"></span><img alt=\"\"><span></span>";
      card.querySelector(".de-card-check").textContent = isBulkSelected ? "✓" : "";
      card.querySelector("img").src = item.image_url;
      card.querySelector("img").alt = item.name;
      card.querySelector("span:last-child").textContent = item.name;
      card.addEventListener("click", (event) => {
        if (event.ctrlKey || event.metaKey || event.shiftKey) {
          toggleItemSelection(item);
          return;
        }
        selectIndex(index);
      });
      card.querySelector(".de-card-check").addEventListener("click", (event) => {
        event.stopPropagation();
        toggleItemSelection(item);
      });
      el.gallery.appendChild(card);
    });
    const pages = galleryPageCount();
    const batchItems = selectedBatchItems();
    el.selectionSummary.textContent = state.selectedPaths.size
      ? `已选 ${batchItems.length} 张`
      : `未选中，将作用于当前筛选结果 ${state.filtered.length} 张`;
    el.selectPage.disabled = pageItems.length === 0;
    el.selectFiltered.disabled = state.filtered.length === 0;
    el.selectAll.disabled = state.items.length === 0;
    el.clearSelection.disabled = state.selectedPaths.size === 0;
    el.galleryFirstPage.disabled = state.galleryPage <= 0;
    el.galleryPrevPage.disabled = state.galleryPage <= 0;
    el.galleryNextPage.disabled = state.galleryPage >= pages - 1;
    el.galleryLastPage.disabled = state.galleryPage >= pages - 1;
    el.galleryPageInput.disabled = !pages;
    el.galleryPageInput.max = String(Math.max(1, pages));
    el.galleryPageInput.value = pages ? String(state.galleryPage + 1) : "1";
    el.galleryPageSize.value = String(state.galleryPageSize);
    el.galleryPageInfo.textContent = pages
      ? `${state.galleryPage + 1} / ${pages} · ${start + 1}-${Math.min(start + pageItems.length, state.filtered.length)}`
      : "0 / 0";
    el.thumbnailFit.textContent = state.thumbnailFit === "cover" ? "填充" : "完整";
    el.thumbnailFit.setAttribute("aria-pressed", state.thumbnailFit === "cover" ? "true" : "false");
  }

  function renderEditor() {
    const item = currentItem();
    el.dirtyFlag.textContent = state.dirty ? "未保存" : "";
    el.save.disabled = !item;
    el.undo.disabled = !state.canUndo;
    el.redo.disabled = !state.canRedo;
    el.prev.disabled = state.selected <= 0;
    el.next.disabled = state.selected < 0 || state.selected >= state.filtered.length - 1;
    el.batch.disabled = state.filtered.length === 0;
    el.taggerTriggerApply.disabled = state.filtered.length === 0 || !el.taggerTrigger.value.trim();

    if (!item) {
      el.preview.innerHTML = "<span>未选择图片</span>";
      el.selectedName.textContent = "-";
      el.caption.value = "";
      return;
    }

    el.preview.innerHTML = "<img alt=\"\">";
    el.preview.querySelector("img").src = item.image_url;
    el.preview.querySelector("img").alt = item.name;
    el.selectedName.textContent = item.relative_path || item.name;
    if (!state.dirty) el.caption.value = item.caption || "";
  }

  function render() {
    el.datasetCount.textContent = `${state.items.length} 张图片`;
    el.filteredCount.textContent = `${state.filtered.length} 个结果`;
    renderTags();
    renderQuickTags();
    renderHistory();
    renderGallery();
    renderEditor();
  }

  function selectIndex(index) {
    if (!confirmDirty()) return;
    state.selected = index;
    state.galleryPage = pageForIndex(index);
    state.dirty = false;
    render();
  }

  function galleryPageCount() {
    return Math.ceil(state.filtered.length / effectiveGalleryPageSize()) || 0;
  }

  function pageForIndex(index) {
    if (index < 0) return 0;
    return Math.floor(index / effectiveGalleryPageSize());
  }

  function changeGalleryPage(delta) {
    goToGalleryPage(state.galleryPage + delta);
  }

  function goToGalleryPage(page) {
    const pages = galleryPageCount();
    if (!pages) return;
    state.galleryPage = Math.min(Math.max(page, 0), pages - 1);
    state.selected = state.galleryPage * effectiveGalleryPageSize();
    state.dirty = false;
    render();
  }

  function setGalleryPageSize(value) {
    if (value === "auto") {
      updateAutoGalleryPageSize();
      const current = currentItem();
      state.galleryPageSize = "auto";
      localStorage.setItem(GALLERY_PAGE_SIZE_KEY, "auto");
      state.galleryPage = current ? pageForIndex(state.filtered.indexOf(current)) : 0;
      render();
      return;
    }
    const nextSize = Number(value);
    if (![12, 15, 20, 24, 30, 48].includes(nextSize)) return;
    const current = currentItem();
    state.galleryPageSize = nextSize;
    localStorage.setItem(GALLERY_PAGE_SIZE_KEY, String(nextSize));
    state.galleryPage = current ? pageForIndex(state.filtered.indexOf(current)) : 0;
    render();
  }

  function toggleThumbnailFit() {
    state.thumbnailFit = state.thumbnailFit === "cover" ? "contain" : "cover";
    localStorage.setItem(THUMBNAIL_FIT_KEY, state.thumbnailFit);
    renderGallery();
  }

  function setSideTab(name) {
    el.sideTabs.forEach((tab) => {
      const active = tab.dataset.sideTab === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    Object.entries(el.sidePanels).forEach(([key, panel]) => {
      if (panel) panel.classList.toggle("is-active", key === name);
    });
  }

  async function refreshHistory() {
    if (!state.root) {
      state.canUndo = false;
      state.canRedo = false;
      state.changes = [];
      renderHistory();
      renderEditor();
      return;
    }
    try {
      const data = await api(API_HISTORY, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ root: state.root }),
      });
      state.canUndo = !!data.can_undo;
      state.canRedo = !!data.can_redo;
      state.changes = data.changes || [];
      renderHistory();
      renderEditor();
    } catch (err) {
      setStatus(err.message, true);
    }
  }

  async function scanDataset() {
    const path = el.path.value.trim();
    if (!path) {
      setStatus("请输入数据集目录。", true);
      return;
    }
    setStatus("正在扫描数据集...");
    try {
      const data = await api("/api/dataset-editor/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      state.root = data.root;
      state.items = data.items || [];
      state.tags = data.tags || [];
      state.categories = data.categories || [];
      state.selectedPaths.clear();
      state.selectionMode = "manual";
      state.selected = state.items.length ? 0 : -1;
      state.galleryPage = 0;
      state.dirty = false;
      el.path.value = state.root;
      renderCategories();
      await refreshHistory();
      applyFilters();
      setStatus(`已加载 ${state.items.length} 张图片。`);
    } catch (err) {
      setStatus(err.message, true);
    }
  }

  async function pickFolder() {
    try {
      const data = await api("/api/pick_file?picker_type=folder");
      if (data.path) {
        el.path.value = data.path;
        await scanDataset();
      }
    } catch (err) {
      setStatus(err.message, true);
    }
  }

  async function saveCaption() {
    const item = currentItem();
    if (!item) return;
    try {
      const data = await api("/api/dataset-editor/caption", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          root: state.root,
          image: item.relative_path,
          caption: el.caption.value,
        }),
      });
      item.caption = data.caption || "";
      item.tags = data.tags || [];
      item.caption_exists = !!data.caption_exists;
      state.dirty = false;
      state.tags = buildTagCounts();
      setStatus("当前 caption 已保存。");
      await refreshHistory();
      applyFilters();
    } catch (err) {
      setStatus(err.message, true);
    }
  }

  function applyChangedItems(items) {
    const byPath = new Map((items || []).map((item) => [item.image, item]));
    state.items.forEach((item) => {
      const changed = byPath.get(item.relative_path);
      if (changed) {
        item.caption = changed.caption || "";
        item.tags = changed.tags || [];
        item.caption_exists = !!changed.caption_exists;
      }
    });
    state.tags = buildTagCounts();
    pruneSelection();
  }

  function buildTagCounts() {
    const counts = new Map();
    state.items.forEach((item) => {
      (item.tags || []).forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1));
    });
    return [...counts.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([tag, count]) => ({ tag, count }));
  }

  async function undoEdit() {
    await applyHistoryAction(API_UNDO, "撤回", "没有可撤回的已保存编辑。");
  }

  async function redoEdit() {
    await applyHistoryAction(API_REDO, "重做", "没有可重做的编辑。");
  }

  async function applyHistoryAction(url, label, emptyMessage) {
    if (!state.root) return;
    if (state.dirty && !window.confirm(`当前输入框有未保存内容，${label}会刷新当前 caption，是否继续？`)) {
      return;
    }
    try {
      const data = await api(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ root: state.root }),
      });
      if (!data.changed) {
        setStatus(emptyMessage);
        await refreshHistory();
        return;
      }
      applyChangedItems(data.items || []);
      state.dirty = false;
      setStatus(`已${label}上一次操作，更新 ${data.changed} 个 caption。`);
      await refreshHistory();
      applyFilters();
    } catch (err) {
      setStatus(err.message, true);
    }
  }

  async function applyBatch() {
    const targets = selectedBatchItems();
    if (!targets.length) return;
    const replace = [];
    if (el.replaceFrom.value.trim()) {
      replace.push({ from: el.replaceFrom.value.trim(), to: el.replaceTo.value.trim() });
    }
    const scope = state.selectedPaths.size ? "已选中" : "当前筛选结果中";
    const ok = window.confirm(`将修改${scope}的 ${targets.length} 张图片，是否继续？`);
    if (!ok) return;
    try {
      const data = await api("/api/dataset-editor/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          root: state.root,
          images: targets.map((item) => item.relative_path),
          append: splitTags(el.append.value),
          remove: splitTags(el.remove.value),
          replace,
          sort: el.sort.checked,
        }),
      });
      applyChangedItems(data.items || []);
      state.dirty = false;
      setStatus(`批量编辑完成，修改 ${data.changed || 0} 张图片。`);
      await refreshHistory();
      applyFilters();
    } catch (err) {
      setStatus(err.message, true);
    }
  }

  async function applyCleanup() {
    const targets = selectedBatchItems();
    if (!targets.length) return;
    const scope = state.selectedPaths.size ? "已选中" : "当前筛选结果中";
    const ok = window.confirm(`将清理${scope}的 ${targets.length} 张图片，是否继续？`);
    if (!ok) return;
    try {
      const data = await api("/api/dataset-editor/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          root: state.root,
          images: targets.map((item) => item.relative_path),
          clean: el.cleanCaption.checked,
          underscore_to_space: el.cleanUnderscore.checked,
          strip_escape_chars: el.cleanEscape.checked,
          sort: el.cleanSort.checked,
        }),
      });
      applyChangedItems(data.items || []);
      state.dirty = false;
      setStatus(`清理完成，修改 ${data.changed || 0} 张图片。`);
      await refreshHistory();
      applyFilters();
    } catch (err) {
      setStatus(err.message, true);
    }
  }

  async function applyTaggerTrigger() {
    const targets = selectedBatchItems();
    const triggerTags = splitTags(el.taggerTrigger.value);
    if (!targets.length || !triggerTags.length) return;
    const scope = state.selectedPaths.size ? "已选中" : "当前筛选结果中";
    const ok = window.confirm(`将额外触发词追加到${scope}的 ${targets.length} 张图片，是否继续？`);
    if (!ok) return;
    try {
      const data = await api("/api/dataset-editor/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          root: state.root,
          images: targets.map((item) => item.relative_path),
          append: splitTags(el.taggerTrigger.value),
        }),
      });
      applyChangedItems(data.items || []);
      state.dirty = false;
      setStatus(`额外触发词已追加，修改 ${data.changed || 0} 张图片。`);
      await refreshHistory();
      applyFilters();
    } catch (err) {
      setStatus(err.message, true);
    }
  }

  function appendTagToCaption(tag) {
    const item = currentItem();
    if (!item) return;
    const tags = splitTags(el.caption.value);
    if (!tags.some((item) => item.toLowerCase() === tag.toLowerCase())) {
      tags.push(tag);
      el.caption.value = tags.join(", ");
      state.dirty = true;
      renderEditor();
    }
  }

  function addQuickTag() {
    const tag = el.quickTagInput.value.trim();
    if (!tag) return;
    state.quickTags = normalizeTagList([tag, ...state.quickTags]).slice(0, 24);
    el.quickTagInput.value = "";
    saveQuickTags();
    renderQuickTags();
    appendTagToCaption(tag);
  }

  el.scan.addEventListener("click", scanDataset);
  el.pick.addEventListener("click", pickFolder);
  el.search.addEventListener("input", applyFilters);
  el.tagToggle.addEventListener("click", () => {
    state.tagExpanded = !state.tagExpanded;
    renderTags();
  });
  el.category.addEventListener("change", applyFilters);
  el.include.addEventListener("input", applyFilters);
  el.exclude.addEventListener("input", applyFilters);
  el.caption.addEventListener("input", () => {
    state.dirty = true;
    renderEditor();
  });
  el.save.addEventListener("click", saveCaption);
  el.undo.addEventListener("click", undoEdit);
  el.redo.addEventListener("click", redoEdit);
  el.galleryFirstPage.addEventListener("click", () => goToGalleryPage(0));
  el.galleryPrevPage.addEventListener("click", () => changeGalleryPage(-1));
  el.galleryPageSize.addEventListener("change", () => setGalleryPageSize(el.galleryPageSize.value));
  el.galleryNextPage.addEventListener("click", () => changeGalleryPage(1));
  el.galleryLastPage.addEventListener("click", () => goToGalleryPage(galleryPageCount() - 1));
  el.galleryPageInput.addEventListener("change", () => goToGalleryPage(Number(el.galleryPageInput.value) - 1));
  el.galleryPageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") goToGalleryPage(Number(el.galleryPageInput.value) - 1);
  });
  el.thumbnailFit.addEventListener("click", toggleThumbnailFit);
  el.selectPage.addEventListener("click", selectPageItems);
  el.selectFiltered.addEventListener("click", selectFilteredItems);
  el.selectAll.addEventListener("click", selectAllItems);
  el.clearSelection.addEventListener("click", clearSelection);
  el.sideTabs.forEach((tab) => tab.addEventListener("click", () => setSideTab(tab.dataset.sideTab)));
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(() => {
      const previous = state.autoGalleryPageSize;
      updateAutoGalleryPageSize();
      if (state.galleryPageSize === "auto" && previous !== state.autoGalleryPageSize) {
        state.galleryPage = Math.min(state.galleryPage, Math.max(0, galleryPageCount() - 1));
        render();
      }
    }).observe(el.gallery);
  }
  window.addEventListener("resize", () => {
    const previous = state.autoGalleryPageSize;
    updateAutoGalleryPageSize();
    if (state.galleryPageSize === "auto" && previous !== state.autoGalleryPageSize) {
      state.galleryPage = Math.min(state.galleryPage, Math.max(0, galleryPageCount() - 1));
      render();
    }
  });
  el.prev.addEventListener("click", () => selectIndex(state.selected - 1));
  el.next.addEventListener("click", () => selectIndex(state.selected + 1));
  el.batch.addEventListener("click", applyBatch);
  el.taggerTrigger.addEventListener("input", renderEditor);
  el.taggerTrigger.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      applyTaggerTrigger();
    }
  });
  el.taggerTriggerApply.addEventListener("click", applyTaggerTrigger);
  el.cleanup.addEventListener("click", applyCleanup);
  el.quickTagAdd.addEventListener("click", addQuickTag);
  el.quickTagInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addQuickTag();
    }
  });
  document.addEventListener("keydown", (event) => {
    const key = event.key.toLowerCase();
    if ((event.ctrlKey || event.metaKey) && !event.shiftKey && key === "z") {
      event.preventDefault();
      undoEdit();
      setStatus("Ctrl+Z: 正在撤回上一条已保存编辑。");
    }
    if ((event.ctrlKey || event.metaKey) && (key === "y" || (event.shiftKey && key === "z"))) {
      event.preventDefault();
      redoEdit();
      setStatus("正在重做上一条撤回编辑。");
    }
  });

  renderCategories();
  updateAutoGalleryPageSize();
  render();
  }

  window.sdDatasetEditor = window.sdDatasetEditor || {};
  window.sdDatasetEditor.init = initDatasetEditor;
  initDatasetEditor();
})();
