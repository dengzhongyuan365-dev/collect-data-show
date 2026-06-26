const state = {
  items: [],
  graph: null,
  config: null,
  category: "",
  topic: "",
  concept: "",
  query: "",
  priority: "",
  sort: "priority",
  selectedUrl: ""
};

const elements = {
  appName: document.querySelector("#appName"),
  appDescription: document.querySelector("#appDescription"),
  categoryNav: document.querySelector("#categoryNav"),
  conceptCloud: document.querySelector("#conceptCloud"),
  topicStrip: document.querySelector("#topicStrip"),
  itemList: document.querySelector("#itemList"),
  detailPane: document.querySelector("#detailPane"),
  viewTitle: document.querySelector("#viewTitle"),
  viewSubtitle: document.querySelector("#viewSubtitle"),
  totalCount: document.querySelector("#totalCount"),
  categoryCount: document.querySelector("#categoryCount"),
  conceptCount: document.querySelector("#conceptCount"),
  filteredCount: document.querySelector("#filteredCount"),
  searchInput: document.querySelector("#searchInput"),
  priorityFilter: document.querySelector("#priorityFilter"),
  sortSelect: document.querySelector("#sortSelect"),
  exportMarkdown: document.querySelector("#exportMarkdown")
};

const PRIORITY_SCORE = {
  "精读": 3,
  "略读": 2,
  "待判断": 1,
  "高": 3,
  "中": 2,
  "低": 1
};

const DEFAULT_CONFIG = {
  title: "数据展示工作台",
  description: "把结构化数据变成可以浏览、搜索和导出的资料库",
  dataFile: "items.json",
  graphFile: "graph.json",
  fields: {
    id: "id",
    title: "title",
    url: "url",
    author: "author",
    category: "category",
    collections: "collections",
    summary: "summary",
    reason: "reason",
    priority: "readingPriority",
    concepts: "concepts",
    topic: "topic",
    cover: "cover"
  },
  labels: {
    item: "条目",
    allItems: "全部条目",
    category: "分类",
    concept: "概念",
    source: "来源",
    reason: "保留理由",
    summary: "摘要",
    openOriginal: "打开原文",
    exportFilename: "data-view.md"
  }
};

document.addEventListener("DOMContentLoaded", init);

async function init() {
  bindEvents();
  await loadData();
  render();
}

function bindEvents() {
  elements.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value.trim().toLowerCase();
    renderMain();
  });

  elements.priorityFilter.addEventListener("change", (event) => {
    state.priority = event.target.value;
    renderMain();
  });

  elements.sortSelect.addEventListener("change", (event) => {
    state.sort = event.target.value;
    renderMain();
  });

  elements.exportMarkdown.addEventListener("click", exportCurrentMarkdown);
}

async function loadData() {
  const config = {
    ...DEFAULT_CONFIG,
    ...(await fetchJson("./config.json").catch(() => ({})))
  };
  config.fields = { ...DEFAULT_CONFIG.fields, ...(config.fields || {}) };
  config.labels = { ...DEFAULT_CONFIG.labels, ...(config.labels || {}) };

  const [rawItems, graph] = await Promise.all([
    fetchJson(`./${config.dataFile || "items.json"}`),
    fetchJson(`./${config.graphFile || "graph.json"}`).catch(() => null)
  ]);

  state.config = config;
  const items = Array.isArray(rawItems) ? rawItems : rawItems.items || rawItems.data || [];
  state.items = items.map(normalizeItem);
  state.graph = graph;
  document.title = config.title;
  elements.appName.textContent = config.title;
  elements.appDescription.textContent = config.description;
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`加载失败：${url}`);
  }
  return response.json();
}

function normalizeItem(item) {
  const fields = state.config.fields;
  const rawConcepts = getPath(item, fields.concepts);
  const concepts = Array.isArray(rawConcepts)
    ? rawConcepts.filter(Boolean).map(String)
    : String(rawConcepts || "").split(/[,，、\s]+/).filter(Boolean);
  const rawCollections = getPath(item, fields.collections);
  const collections = Array.isArray(rawCollections)
    ? rawCollections.filter(Boolean).map(String)
    : String(rawCollections || "").split(/[,，、]+/).filter(Boolean);
  const title = cleanText(getPath(item, fields.title) || "未命名条目");
  const url = cleanText(getPath(item, fields.url) || getPath(item, fields.id) || "");
  const summary = decodeHtml(cleanText(getPath(item, fields.summary) || getPath(item, "description") || getPath(item, "excerpt") || ""));
  const cover = normalizeAssetUrl(cleanText(getPath(item, fields.cover) || ""));
  return {
    id: getPath(item, fields.id) || url || title,
    title,
    url,
    author: cleanText(getPath(item, fields.author) || ""),
    category: cleanText(getPath(item, fields.category) || "未分类"),
    collections,
    summary,
    cover,
    reason: cleanText(getPath(item, fields.reason) || ""),
    readingPriority: cleanText(getPath(item, fields.priority) || "待判断"),
    concepts,
    topic: cleanText(getPath(item, fields.topic) || "") || inferTopic({ ...item, title, summary, category: getPath(item, fields.category) }, concepts)
  };
}

function inferTopic(item, concepts) {
  const title = `${item.title || ""} ${item.summary || ""}`;
  const rules = [
    ["Claude Code", /claude\s*code|claudecode/i],
    ["Agent", /agent|智能体|代理/i],
    ["Prompt", /prompt|提示词/i],
    ["Linux", /linux|内核|kernel|systemd|gdb|qemu|网络协议|coredump/i],
    ["C++", /c\+\+|cpp|stl|并发|线程池/i],
    ["开源项目", /github|开源|star/i],
    ["职业发展", /职场|职业|面试|简历|工资|薪资/i],
    ["学习方法", /学习|教程|指南|方法|路线/i],
    ["产品设计", /产品|设计|交互|用户体验/i],
    ["心理成长", /心理|情绪|焦虑|成长|认知/i]
  ];

  for (const [topic, pattern] of rules) {
    if (pattern.test(title)) {
      return topic;
    }
  }

  return concepts[0] || item.category || "未归档";
}

function render() {
  renderStats();
  renderCategoryNav();
  renderConceptCloud();
  renderMain();
}

function renderStats() {
  elements.totalCount.textContent = String(state.items.length);
  elements.categoryCount.textContent = String(groupCount(state.items, "category").length);
  elements.conceptCount.textContent = String(getConceptCounts(state.items).length);
}

function renderCategoryNav() {
  const categories = [["", state.items.length], ...groupCount(state.items, "category")];
  elements.categoryNav.innerHTML = "";

  for (const [category, count] of categories) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `nav-item ${state.category === category ? "active" : ""}`.trim();
    button.innerHTML = `<span>${category || state.config.labels.allItems}</span><span class="count">${count}</span>`;
    button.addEventListener("click", () => {
      state.category = category;
      state.topic = "";
      state.concept = "";
      render();
    });
    elements.categoryNav.appendChild(button);
  }
}

function renderConceptCloud() {
  const sourceItems = state.category
    ? state.items.filter((item) => item.category === state.category)
    : state.items;
  const concepts = getConceptCounts(sourceItems).slice(0, 42);
  elements.conceptCloud.innerHTML = "";

  for (const [concept, count] of concepts) {
    const chip = createChip(`${concept} ${count}`, state.concept === concept);
    chip.addEventListener("click", () => {
      state.concept = state.concept === concept ? "" : concept;
      state.topic = "";
      renderMain();
      renderConceptCloud();
    });
    elements.conceptCloud.appendChild(chip);
  }
}

function renderMain() {
  const items = getFilteredItems();
  elements.filteredCount.textContent = String(items.length);
  elements.viewTitle.textContent = buildViewTitle();
  elements.viewSubtitle.textContent = buildViewSubtitle(items);
  renderTopicStrip(getFilteredItems({ includeTopic: false }));
  renderItemList(items);
  renderDetail();
}

function buildViewTitle() {
  if (state.topic) {
    return `专题：${state.topic}`;
  }
  if (state.concept) {
    return `概念：${state.concept}`;
  }
  if (state.category) {
    return state.category;
  }
  return state.config.labels.allItems;
}

function buildViewSubtitle(items) {
  const parts = [`当前 ${items.length} ${state.config.labels.item}`];
  if (state.priority) {
    parts.push(`优先级：${state.priority}`);
  }
  if (state.topic) {
    parts.push(`专题：${state.topic}`);
  }
  if (state.query) {
    parts.push(`搜索：${state.query}`);
  }
  return parts.join(" / ");
}

function renderTopicStrip(items) {
  const topics = groupCount(items, "topic").slice(0, 28);
  elements.topicStrip.innerHTML = "";

  if (!topics.length) {
    return;
  }

  const allChip = createChip("全部专题", !state.topic);
  allChip.addEventListener("click", () => {
    state.topic = "";
    renderMain();
    renderConceptCloud();
  });
  elements.topicStrip.appendChild(allChip);

  for (const [topic, count] of topics) {
    const chip = createChip(`${topic} ${count}`, state.topic === topic);
    chip.addEventListener("click", () => {
      state.topic = state.topic === topic ? "" : topic;
      renderMain();
      renderConceptCloud();
    });
    elements.topicStrip.appendChild(chip);
  }
}

function renderItemList(items) {
  elements.itemList.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = `没有匹配的${state.config.labels.item}。`;
    elements.itemList.appendChild(empty);
    return;
  }

  for (const item of items) {
    elements.itemList.appendChild(createItemCard(item));
  }
}

function createItemCard(item) {
  const card = document.createElement("article");
  const priorityName = item.readingPriority === "精读"
    ? "priority-card-strong"
    : item.readingPriority === "略读"
      ? "priority-card-normal"
      : "priority-card-muted";
  card.className = `item-card ${priorityName} ${state.selectedUrl === item.url ? "selected" : ""}`.trim();
  card.addEventListener("click", () => {
    state.selectedUrl = item.url;
    renderItemList(getFilteredItems());
    renderDetail();
  });

  const title = document.createElement("a");
  title.className = "item-title";
  title.href = item.url;
  title.target = "_blank";
  title.rel = "noreferrer";
  title.textContent = item.title;
  title.addEventListener("click", (event) => event.stopPropagation());

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.appendChild(createBadge(item.category, "category"));
  meta.appendChild(createBadge(item.readingPriority, priorityClass(item.readingPriority)));
  if (item.topic) {
    meta.appendChild(createBadge(item.topic));
  }
  if (item.author) {
    meta.appendChild(createBadge(item.author));
  }

  const summary = document.createElement("div");
  summary.className = "summary";
  summary.textContent = trimText(item.summary || `暂无${state.config.labels.summary}。`, 220);

  const footer = document.createElement("div");
  footer.className = "card-footer";
  const concepts = document.createElement("span");
  concepts.className = "badge";
  concepts.textContent = item.concepts.slice(0, 3).join(" / ") || "无概念";
  const open = document.createElement("a");
  open.className = "open-link";
  open.href = item.url;
  open.target = "_blank";
  open.rel = "noreferrer";
  open.textContent = state.config.labels.openOriginal;
  open.addEventListener("click", (event) => event.stopPropagation());
  footer.append(concepts, open);

  if (item.cover) {
    const coverLink = document.createElement("a");
    coverLink.className = "item-cover";
    coverLink.href = item.url;
    coverLink.target = "_blank";
    coverLink.rel = "noreferrer";
    coverLink.addEventListener("click", (event) => event.stopPropagation());
    const image = document.createElement("img");
    image.src = item.cover;
    image.alt = item.title;
    image.loading = "lazy";
    coverLink.appendChild(image);
    card.appendChild(coverLink);
  }

  card.append(title, meta, summary, footer);
  return card;
}

function renderDetail() {
  const item = state.items.find((entry) => entry.url === state.selectedUrl);
  if (!item) {
    elements.detailPane.innerHTML = `
      <div class="empty-detail">
        <strong>选择一个${state.config.labels.item}</strong>
        <span>这里会显示${state.config.labels.summary}、${state.config.labels.concept}和链接。</span>
      </div>
    `;
    return;
  }

  elements.detailPane.innerHTML = "";

  const title = document.createElement("h2");
  title.className = "detail-title";
  title.textContent = item.title;

  const meta = document.createElement("div");
  meta.className = "meta detail-section";
  meta.appendChild(createBadge(item.category, "category"));
  meta.appendChild(createBadge(item.readingPriority, priorityClass(item.readingPriority)));
  if (item.author) {
    meta.appendChild(createBadge(item.author));
  }

  const open = document.createElement("a");
  open.className = "open-link";
  open.href = item.url;
  open.target = "_blank";
  open.rel = "noreferrer";
  open.textContent = state.config.labels.openOriginal;

  if (item.cover) {
    const cover = document.createElement("img");
    cover.className = "detail-cover";
    cover.src = item.cover;
    cover.alt = item.title;
    elements.detailPane.appendChild(cover);
  }

  const concepts = createDetailSection(state.config.labels.concept, item.concepts.length ? item.concepts.join("、") : `暂无${state.config.labels.concept}`);
  const collections = createDetailSection(state.config.labels.source, item.collections.length ? item.collections.join("、") : "未知");
  const reason = createDetailSection(state.config.labels.reason, item.reason || `暂无${state.config.labels.reason}。`);
  const summary = createDetailSection(state.config.labels.summary, item.summary || `暂无${state.config.labels.summary}。`, true);

  elements.detailPane.append(title, meta, concepts, collections, reason, summary, open);
}

function createDetailSection(title, text, isLong = false) {
  const section = document.createElement("section");
  section.className = "detail-section";
  const heading = document.createElement("h3");
  heading.textContent = title;
  const body = document.createElement("div");
  body.className = isLong ? "detail-summary" : "";
  body.textContent = text;
  section.append(heading, body);
  return section;
}

function getFilteredItems(options = {}) {
  const includeTopic = options.includeTopic !== false;
  const query = state.query;
  return state.items
    .filter((item) => !state.category || item.category === state.category)
    .filter((item) => !state.priority || item.readingPriority === state.priority)
    .filter((item) => !includeTopic || !state.topic || item.topic === state.topic)
    .filter((item) => {
      if (!state.concept) {
        return true;
      }
      return item.concepts.includes(state.concept);
    })
    .filter((item) => {
      if (!query) {
        return true;
      }
      const haystack = [
        item.title,
        item.author,
        item.category,
        item.topic,
        item.summary,
        item.concepts.join(" ")
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    })
    .sort(sortItems);
}

function sortItems(left, right) {
  if (state.sort === "title") {
    return left.title.localeCompare(right.title, "zh-CN");
  }
  if (state.sort === "author") {
    return left.author.localeCompare(right.author, "zh-CN") || left.title.localeCompare(right.title, "zh-CN");
  }
  return (PRIORITY_SCORE[right.readingPriority] || 0) - (PRIORITY_SCORE[left.readingPriority] || 0)
    || left.category.localeCompare(right.category, "zh-CN")
    || left.title.localeCompare(right.title, "zh-CN");
}

function groupCount(items, key) {
  const counts = new Map();
  for (const item of items) {
    const value = item[key] || "未分类";
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  return Array.from(counts.entries()).sort((left, right) => {
    return right[1] - left[1] || left[0].localeCompare(right[0], "zh-CN");
  });
}

function getConceptCounts(items) {
  const counts = new Map();
  for (const item of items) {
    for (const concept of item.concepts) {
      counts.set(concept, (counts.get(concept) || 0) + 1);
    }
  }
  return Array.from(counts.entries()).sort((left, right) => {
    return right[1] - left[1] || left[0].localeCompare(right[0], "zh-CN");
  });
}

function createChip(text, active = false) {
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = `chip ${active ? "active" : ""}`.trim();
  chip.textContent = text;
  return chip;
}

function createBadge(text, extraClass = "") {
  const badge = document.createElement("span");
  badge.className = `badge ${extraClass}`.trim();
  badge.textContent = text || "未知";
  return badge;
}

function priorityClass(priority) {
  if (priority === "精读") {
    return "priority-strong";
  }
  if (priority === "略读") {
    return "priority-normal";
  }
  return "";
}

function exportCurrentMarkdown() {
  const items = getFilteredItems();
  if (!items.length) {
    return;
  }

  const lines = [
    `# ${buildViewTitle()}`,
    "",
    `导出时间：${new Date().toLocaleString("zh-CN")}`,
    `${state.config.labels.item}数量：${items.length}`,
    ""
  ];

  const grouped = groupItemsForExport(items);
  for (const [group, entries] of grouped) {
    lines.push(`## ${group}`, "");
    for (const item of entries) {
      lines.push(`- [${item.title}](${item.url})`);
      lines.push(`  - 作者：${item.author || "未知"}；优先级：${item.readingPriority}；分类：${item.category}`);
      if (item.concepts.length) {
        lines.push(`  - 概念：${item.concepts.slice(0, 8).join("、")}`);
      }
      lines.push(`  - ${state.config.labels.summary}：${trimText(item.summary, 180)}`);
    }
    lines.push("");
  }

  downloadText(state.config.labels.exportFilename || "data-view.md", lines.join("\n"), "text/markdown");
}

function groupItemsForExport(items) {
  const map = new Map();
  for (const item of items) {
    const group = state.category ? item.topic : item.category;
    if (!map.has(group)) {
      map.set(group, []);
    }
    map.get(group).push(item);
  }
  return Array.from(map.entries()).sort((left, right) => {
    return right[1].length - left[1].length || left[0].localeCompare(right[0], "zh-CN");
  });
}

function downloadText(filename, text, mimeType) {
  const blob = new Blob([text], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function cleanText(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

function trimText(text, maxLength) {
  const value = cleanText(text);
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength)}...`;
}

function decodeHtml(text) {
  const textarea = document.createElement("textarea");
  textarea.innerHTML = text;
  return textarea.value;
}

function normalizeAssetUrl(url) {
  const text = cleanText(url);
  if (text.startsWith("//")) {
    return `https:${text}`;
  }
  return text;
}

function getPath(object, path) {
  if (!path) {
    return undefined;
  }
  if (!String(path).includes(".")) {
    return object?.[path];
  }
  return String(path)
    .split(".")
    .reduce((value, key) => value == null ? undefined : value[key], object);
}
