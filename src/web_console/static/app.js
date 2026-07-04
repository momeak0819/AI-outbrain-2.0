const $ = (id) => document.getElementById(id);

const ROUTES = {
  dashboard: { title: "工作台总览", crumb: "工作台 / 总览" },
  settings: { title: "初始化 / 设置", crumb: "设置 / 初始化" },
  sources: { title: "信源与获取", crumb: "五层架构 / Source + Acquisition" },
  processing: { title: "处理与模型", crumb: "五层架构 / Processing" },
  knowledge: { title: "知识与交付", crumb: "五层架构 / Knowledge + Delivery" },
  "project-memory": { title: "项目记忆", crumb: "知识库 / 08_项目映射库" },
  system: { title: "系统与发布", crumb: "系统 / 发布检查" },
};

const SOURCE_LABELS = {
  bilibili: "B站",
  douyin: "抖音",
  generic_video: "通用视频链接",
  instagram: "Instagram",
  local_audio: "本地音频 / MP4",
  text_input: "普通文字输入",
  tiktok: "TikTok",
  twitch: "Twitch",
  vimeo: "Vimeo",
  x_video: "X / Twitter",
  xiaohongshu: "小红书",
  youtube: "YouTube",
};

const BACKEND_LABELS = {
  dedicated_douyin: "专用链路",
  local_file: "本地文件",
  text_protocol: "文本输入协议",
  yt_dlp: "yt-dlp",
};

const STATUS_LABELS = {
  implemented: "已实现",
  planned: "计划中",
  reserved: "预留",
  basic_acquisition: "基础获取已接入",
  completed: "已完成",
  failed: "失败",
  skipped: "已跳过",
  ready: "就绪",
  transcript_ready: "文字稿已就绪",
  pending_draft: "等待草稿",
  approved: "已批准",
  cancelled: "已取消",
  finalized: "已归档",
};

const HEALTH_LABELS = {
  not_checked: "未检查",
  not_configured: "未配置",
  configured: "已配置",
  ready: "本地就绪",
  needs_cookie: "需要 Cookies",
  reserved: "预留",
  unavailable: "不可用",
};

const PROVIDER_LABELS = {
  project: "项目内置",
  local: "本地",
  xiaomi: "小米",
  custom: "自定义",
  aliyun: "阿里云",
  tencent_cloud: "腾讯云",
  volcengine: "火山引擎",
};

const ASR_LABELS = {
  mock: "Mock 测试引擎",
  faster_whisper: "本地 faster-whisper",
  mimo: "小米 MiMo ASR",
  custom_api: "自定义 ASR API",
  aliyun_qwen_asr: "阿里云 Qwen-ASR",
  tencent_asr: "腾讯云 ASR",
  volcengine_asr: "火山引擎 ASR",
};

const CONTENT_MODE_LABELS = {
  original: "原文模式",
  card: "卡片模式",
  both: "双输出",
};

const EXPORT_LABELS = {
  md: "Markdown",
  txt: "TXT",
  both: "Markdown + TXT",
};

const LAYER_LABELS = {
  source: "信源 Source",
  acquisition: "获取 Acquisition",
  processing: "处理 Processing",
  knowledge: "知识 Knowledge",
  delivery: "交付 Delivery",
};

let appState = {
  status: {},
  capabilities: {},
  route12: {},
  sourceSettings: {},
  knowledgeStructure: {},
  reviews: {},
  projectMemory: {},
  agentSetup: {},
  projectMemoryChallenge: {},
  projectMemoryConnection: {},
  lastIngest: null,
};

function label(map, value) {
  return map[value] || value || "";
}

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function getJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  return response.json();
}

function pill(name, value) {
  return `<div class="pill"><strong>${escapeHTML(name)}</strong><span>${escapeHTML(value ?? "")}</span></div>`;
}

function badge(text, tone = "neutral") {
  return `<span class="badge ${tone}">${escapeHTML(text)}</span>`;
}

function renderJSON(id, payload) {
  $(id).textContent = JSON.stringify(payload, null, 2);
}

async function copyText(value) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return true;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  return ok;
}

function currentRoute() {
  const raw = location.hash.replace("#/", "") || "dashboard";
  return ROUTES[raw] ? raw : "dashboard";
}

function setRoute(route) {
  const normalized = ROUTES[route] ? route : "dashboard";
  document.querySelectorAll(".page").forEach((page) => {
    page.classList.toggle("active", page.dataset.page === normalized);
  });
  document.querySelectorAll(".nav a").forEach((link) => {
    link.classList.toggle("active", link.dataset.route === normalized);
  });
  $("page-title").textContent = ROUTES[normalized].title;
  $("breadcrumb").textContent = ROUTES[normalized].crumb;
  if (normalized === "project-memory") {
    ensureAgentSetupLoaded().catch(() => {});
  }
}

async function refreshAll() {
  const [status, capabilities, route12, sourceSettings, knowledgeStructure] = await Promise.all([
    getJSON("/api/status"),
    getJSON("/api/capabilities"),
    getJSON("/api/route12"),
    getJSON("/api/source-settings"),
    getJSON("/api/knowledge-structure"),
  ]);
  appState.status = status;
  appState.capabilities = capabilities;
  appState.route12 = route12;
  appState.sourceSettings = sourceSettings;
  appState.knowledgeStructure = knowledgeStructure;
  try {
    appState.projectMemory = await getJSON("/api/project-memory");
  } catch {
    appState.projectMemory = {};
  }
  try {
    const selectedAgent = $("agent-setup-select")?.value || "generic";
    appState.agentSetup = await getJSON(`/api/project-memory/agent-setup?agent=${encodeURIComponent(selectedAgent)}`);
  } catch {
    appState.agentSetup = {};
  }
  renderAll();
}

function renderAll() {
  renderTopStatus();
  renderDashboard();
  renderSources();
  renderAsrProviders();
  renderProcessingFeatures();
  renderKnowledgeStructure();
  renderProjectMemory();
  renderRoute12();
  renderDeliveryPreview();
  renderSystemInfo();
  renderManifestSummary();
  const route = currentRoute();
  if (!appState.status.initialized && route === "dashboard") {
    location.hash = "#/settings";
    return;
  }
  setRoute(route);
}

function renderTopStatus() {
  const status = appState.status || {};
  const route = appState.route12 || {};
  $("top-status").innerHTML = [
    badge(status.initialized ? "已初始化" : "未初始化", status.initialized ? "ok" : "warn"),
    badge(route.mcp_ready ? "MCP 已验证" : "MCP 未就绪", route.mcp_ready ? "ok" : "warn"),
    badge(label(ASR_LABELS, status.asr?.engine) || "ASR 未配置", "neutral"),
  ].join("");
}

function renderDashboard() {
  const status = appState.status || {};
  const caps = appState.capabilities || {};
  const route = appState.route12 || {};
  const sources = caps.source_matrix || [];
  const providers = caps.asr_providers || [];
  const ytdlpCount = sources.filter((item) => item.backend === "yt_dlp").length;

  $("dashboard-notice").innerHTML = status.initialized
    ? "系统已完成初始化。你可以从“信源与获取”开始运行 ingest，或在“知识与交付”查看 MCP 与审核状态。"
    : "首次使用需要先完成初始化。请进入“初始化 / 设置”页面保存配置。";

  $("dashboard-kpis").innerHTML = [
    metric("初始化", status.initialized ? "已完成" : "待配置", status.initialized ? "ok" : "warn"),
    metric("当前 ASR", label(ASR_LABELS, status.asr?.engine) || "未配置", "neutral"),
    metric("信源能力", `${sources.length} 个`, "neutral"),
    metric("yt-dlp 信源", `${ytdlpCount} 个`, "neutral"),
    metric("ASR 服务", `${providers.length} 个`, "neutral"),
    metric("MCP", route.mcp_ready ? "已验证" : "未就绪", route.mcp_ready ? "ok" : "warn"),
  ].join("");

  renderFlowCards(appState.lastIngest);
  $("dashboard-sources").innerHTML = compactSourceList(sources);
  $("dashboard-next").innerHTML = nextActionBlock(status, route);
}

function metric(title, value, tone) {
  return `<div class="metric ${tone}">
    <span>${escapeHTML(title)}</span>
    <strong>${escapeHTML(value)}</strong>
  </div>`;
}

function renderFlowCards(payload) {
  const layers = ["source", "acquisition", "processing", "knowledge", "delivery"];
  $("flow-cards").innerHTML = layers.map((layer) => {
    const item = payload?.[layer] || {};
    const failed = item.status === "failed" || item.error || item.error_code;
    const state = item.status ? label(STATUS_LABELS, item.status) : "等待运行";
    return `<div class="flow-card ${failed ? "failed" : ""}">
      <strong>${label(LAYER_LABELS, layer)}</strong>
      <span>${escapeHTML(state)}</span>
      <small>${escapeHTML(item.error_code || "")}</small>
    </div>`;
  }).join("");
}

function compactSourceList(sources) {
  if (!sources.length) return '<p class="muted">暂无信源清单。</p>';
  return `<div class="tag-list">${sources.map((item) =>
    `<span>${escapeHTML(item.display_name || label(SOURCE_LABELS, item.source_type) || item.source_type)}</span>`
  ).join("")}</div>`;
}

function nextActionBlock(status, route) {
  if (!status.initialized) {
    return '<p>下一步：进入 <a href="#/settings">初始化 / 设置</a> 完成配置。</p>';
  }
  if (!route.mcp_ready) {
    return '<p>下一步：如需 card / both，请在“知识与交付”完成 MCP 连接验证。</p>';
  }
  return '<p>下一步：从“信源与获取”输入链接或本地文件，开始五层处理流程。</p>';
}

function renderSources() {
  const sources = appState.capabilities.source_matrix || [];
  $("source-radar").innerHTML = renderRadar(sources, "信源健康度");
  $("source-cards").innerHTML = sources.map(sourceCard).join("");
}

function sourceCard(row) {
  const needsCookie = row.cookie_required;
  const cookieText = needsCookie
    ? (row.cookie_configured ? "Cookies 已配置" : "需要 Cookies")
    : "通常不需要 Cookies";
  const tone = row.health === "needs_cookie" ? "warn" : row.health === "reserved" ? "neutral" : "ok";
  return `<article class="capability-card ${row.health}">
    <div class="card-head">
      <div>
        <strong>${escapeHTML(row.display_name || label(SOURCE_LABELS, row.source_type))}</strong>
        <small>${escapeHTML(row.source_type)} · ${escapeHTML(row.kind || "")}</small>
      </div>
      ${badge(label(HEALTH_LABELS, row.health), tone)}
    </div>
    <p>${escapeHTML(row.display_status || label(STATUS_LABELS, row.status))}</p>
    <div class="mini-row">
      <span>${escapeHTML(cookieText)}</span>
      <span>${escapeHTML(label(BACKEND_LABELS, row.backend))}</span>
    </div>
    ${needsCookie ? `<button type="button" class="ghost" data-config-cookie="${escapeHTML(row.source_type)}">配置 Cookies</button>` : ""}
  </article>`;
}

function renderCookiePanel(sourceType) {
  const rows = appState.capabilities.source_matrix || [];
  const row = rows.find((item) => item.source_type === sourceType);
  if (!row) return;
  const settingsRows = appState.sourceSettings.sources || [];
  const current = settingsRows.find((item) => item.source_type === sourceType) || {};
  const loginUrl = current.login_url || row.login_url || "";
  $("source-settings-panel").innerHTML = `<div class="card embedded">
    <div class="section-title">
      <div>
        <h3>配置 ${escapeHTML(row.display_name)} Cookies</h3>
        <p>按 yt-dlp 官方方式，优先使用 --cookies-from-browser：先在浏览器登录平台，再让 yt-dlp 在获取内容时自动读取该浏览器登录态。这里不导出、不展示 Cookie 内容。</p>
      </div>
      <button type="button" class="ghost" id="close-source-settings">关闭</button>
    </div>
    <form id="source-settings-form" class="form-grid compact">
      <input type="hidden" name="source_type" value="${escapeHTML(sourceType)}" />
      <input type="hidden" name="cookie_ready" value="${current.cookie_configured ? "true" : "false"}" />
      <label>从浏览器读取 Cookies（推荐）
        <select name="cookies_from_browser">
          <option value="">不使用浏览器 Cookies</option>
          <option value="edge" ${current.cookies_from_browser === "edge" ? "selected" : ""}>Microsoft Edge（推荐 Windows 用户）</option>
          <option value="chrome" ${current.cookies_from_browser === "chrome" ? "selected" : ""}>Google Chrome</option>
          <option value="firefox" ${current.cookies_from_browser === "firefox" ? "selected" : ""}>Firefox</option>
          <option value="brave" ${current.cookies_from_browser === "brave" ? "selected" : ""}>Brave</option>
          <option value="vivaldi" ${current.cookies_from_browser === "vivaldi" ? "selected" : ""}>Vivaldi</option>
        </select>
      </label>
      <div class="cookie-flow full-row ${current.cookie_configured ? "ready" : ""}" id="cookie-flow-state">
        <div>
          <strong>${current.cookie_configured ? "浏览器 Cookie 来源已配置" : "等待选择浏览器 Cookie 来源"}</strong>
          <p>${current.cookie_configured ? "yt-dlp 会在解析/下载该平台内容时，从所选浏览器自动读取登录态；本系统不会输出 Cookie 内容。" : "请先选择浏览器，再打开平台登录页完成扫码/登录，最后确认使用该浏览器作为 Cookie 来源。"}</p>
        </div>
        <div class="cookie-flow-actions">
          <button type="button" class="ghost" data-open-login="${escapeHTML(loginUrl)}" ${loginUrl ? "" : "disabled"}>打开登录页</button>
          <button type="button" class="ghost" id="prepare-cookie-config">我已登录，使用该浏览器 Cookie 来源</button>
        </div>
      </div>
      <label>Cookie 文件路径
        <div class="path-picker">
          <input name="cookies_file" placeholder="备用方案：Netscape cookies.txt 文件路径" />
          <button type="button" data-pick-file="cookies_file">选择 Cookie 文件</button>
        </div>
      </label>
      <div class="cookie-help full-row">
        <strong>操作指引</strong>
        <ol>
          <li>先在 Edge / Chrome / Firefox 中登录 ${escapeHTML(row.display_name)}。</li>
          <li>回到这里点击“使用该浏览器 Cookie 来源”，状态会由白色变成蓝色。</li>
          <li>确认变蓝后点击保存；真正读取 Cookie 会发生在 yt-dlp 解析/下载内容时。</li>
          <li>如果浏览器来源不可用，再使用 cookies.txt 文件作为备用。</li>
          <li>系统只保存路径或浏览器名称，不保存 Cookie 内容。</li>
        </ol>
      </div>
      <button type="submit">保存 Cookies 配置</button>
    </form>
    <pre id="source-settings-result"></pre>
  </div>`;
}

function renderAsrProviders() {
  const providers = appState.capabilities.asr_providers || [];
  $("asr-radar").innerHTML = renderRadar(providers.map((item) => ({
    display_name: item.display_name || label(ASR_LABELS, item.engine_id),
    health_score: item.health_score,
    health: item.health,
  })), "ASR 服务健康度");
  $("asr-cards").innerHTML = providers.map((row) => {
    const tone = row.configured ? "ok" : "neutral";
    return `<article class="capability-card ${row.configured ? "configured" : "not-configured"}">
      <div class="card-head">
        <div>
          <strong>${escapeHTML(row.display_name || label(ASR_LABELS, row.engine_id))}</strong>
          <small>${escapeHTML(row.engine_id)}</small>
        </div>
        ${badge(row.configured ? "已配置" : "未配置", tone)}
      </div>
      <p>${escapeHTML(label(PROVIDER_LABELS, row.provider))} · ${escapeHTML(row.deployment_type || "")}</p>
      <div class="mini-row">
        <span>${escapeHTML(label(STATUS_LABELS, row.status))}</span>
        <span>${(row.supported_extensions || []).map(escapeHTML).join(", ")}</span>
      </div>
    </article>`;
  }).join("");
}

function renderProcessingFeatures() {
  const features = appState.capabilities.processing_capabilities || [];
  $("processing-features").innerHTML = features.map((item) => `<div class="feature-card ${item.status === "implemented" ? "active" : "future"}">
    <strong>${escapeHTML(item.name)}</strong>
    <span>${item.status === "implemented" ? "已实现" : "预留"}</span>
    <p>${escapeHTML(item.description || "")}</p>
  </div>`).join("");
}

function renderKnowledgeStructure() {
  const categories = appState.knowledgeStructure.categories || [];
  $("knowledge-structure").innerHTML = categories.map((item) => `<article class="capability-card ${item.index_exists ? "ready" : "needs-cookie"}">
    <div class="card-head">
      <div>
        <strong>${escapeHTML(item.name)}</strong>
        <small>${escapeHTML(item.id)}</small>
      </div>
      ${badge(item.index_exists ? "索引存在" : "索引缺失", item.index_exists ? "ok" : "warn")}
    </div>
    <p>${escapeHTML(item.description)}</p>
    <div class="mini-row">
      <span>${item.requires_review ? "正式归档需要审核" : "Inbox / 草稿区"}</span>
      <span>${escapeHTML(item.index)}</span>
    </div>
  </article>`).join("");
}

function renderRadar(items, title) {
  const visible = items.slice(0, 12);
  if (!visible.length) return '<p class="muted">暂无能力数据。</p>';
  const cx = 150;
  const cy = 150;
  const maxR = 105;
  const angleStep = (Math.PI * 2) / visible.length;
  const pointFor = (index, score = 100) => {
    const angle = -Math.PI / 2 + index * angleStep;
    const r = maxR * Math.max(0, Math.min(100, Number(score || 0))) / 100;
    return [cx + Math.cos(angle) * r, cy + Math.sin(angle) * r];
  };
  const axis = visible.map((item, index) => {
    const [x, y] = pointFor(index, 100);
    const [lx, ly] = pointFor(index, 118);
    return `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" />
      <text x="${lx}" y="${ly}" text-anchor="middle">${escapeHTML(item.display_name || item.engine_id || item.source_type || item.name)}</text>`;
  }).join("");
  const rings = [35, 70, 105].map((r) =>
    `<circle cx="${cx}" cy="${cy}" r="${r}" />`
  ).join("");
  const points = visible.map((item, index) => pointFor(index, item.health_score).join(",")).join(" ");
  const dots = visible.map((item, index) => {
    const [x, y] = pointFor(index, item.health_score);
    return `<circle class="radar-dot ${escapeHTML(item.health || "")}" cx="${x}" cy="${y}" r="4" />`;
  }).join("");
  return `<div class="radar-panel">
    <div>
      <h3>${escapeHTML(title)}</h3>
      <p>彩色越靠外，代表本地可判定状态越完整；白色或灰边代表尚未配置或只是预留。</p>
    </div>
    <svg viewBox="0 0 300 300" role="img" aria-label="${escapeHTML(title)}">
      <g class="radar-grid">${rings}${axis}</g>
      <polygon class="radar-area" points="${points}" />
      ${dots}
    </svg>
  </div>`;
}

function renderRoute12() {
  const route = appState.route12 || {};
  $("route12").innerHTML = [
    pill("Vault", route.vault_exists ? "存在" : "缺失"),
    pill("MCP 连接", route.mcp_ready ? "已验证" : "未就绪"),
    pill("知识整理", route.curation_ready ? "可用" : "未就绪"),
    pill("缺失路径", (route.missing_required_paths || []).length),
    pill("下一步", route.recommended_next_step || ""),
  ].join("");
}

function renderDeliveryPreview() {
  const last = appState.lastIngest || {};
  $("delivery-preview").innerHTML = [
    pill("内容模式", label(CONTENT_MODE_LABELS, last.content_mode) || "等待运行"),
    pill("workflow_complete", last.workflow_complete === undefined ? "等待运行" : (last.workflow_complete ? "完成" : "未完成")),
    pill("next_action", last.next_action || "无"),
    pill("next_skill", last.next_skill || "无"),
  ].join("");
}

function renderProjectMemory() {
  const recent = appState.projectMemory.recent || [];
  renderProjectMemoryStatus(appState.projectMemory.status || {});
  renderAgentSetup(appState.agentSetup || {});
  renderAgentSetupVerify(appState.agentSetup || {}, appState.projectMemory.status || {}, recent);
  renderAgentConnectionCard(appState.projectMemoryConnection || {}, appState.projectMemoryChallenge || {});
  const statusContainer = $("project-memory-recent");
  if (statusContainer) {
    statusContainer.innerHTML = "";
  }
  const drafts = $("project-memory-drafts");
  if (!drafts) return;
  drafts.innerHTML = recent.length
    ? recent.map(projectMemoryCard).join("")
    : '<p class="muted">暂无项目记忆。外部 Agent 可通过 project-memory-capture Skill 创建待审核草稿。</p>';
}

function renderProjectMemoryStatus(status) {
  const box = $("project-memory-status");
  if (!box) return;
  const checks = status.checks || {};
  const rows = [
    ["Skill", checks.skill_available],
    ["CLI Capture", checks.cli_capture_available],
    ["待审核区", checks.draft_area_exists],
    ["项目映射库", checks.formal_project_map_exists],
    ["项目记忆模板", checks.project_memory_template_exists],
    ["索引", checks.project_memory_index_exists],
  ];
  box.innerHTML = `<div class="status-card ${status.automation_ready ? "ready" : "warn"}">
    <div>
      <strong>${status.automation_ready ? "工作 Agent 自动化入口已就绪" : "工作 Agent 自动化入口未完全就绪"}</strong>
      <p>${escapeHTML(status.recommended_scheduler || "")}</p>
      <code>${escapeHTML(status.capture_command || "")}</code>
    </div>
    <div class="check-list">
      ${rows.map(([name, ok]) => `<span class="${ok ? "ok" : "warn"}">${ok ? "●" : "○"} ${escapeHTML(name)}</span>`).join("")}
    </div>
  </div>`;
}

function renderAgentSetup(setup) {
  const panel = $("agent-setup-panel");
  if (!panel) return;
  if (!setup.success) {
    panel.innerHTML = '<p class="muted">请选择一个工作 Agent 生成配置说明。</p>';
    return;
  }
  panel.innerHTML = `<div class="agent-template">
    <div class="template-summary">
      ${pill("Agent", setup.display_name || setup.agent || "通用")}
      ${pill("Skill 路径", setup.skill_path || "")}
      ${pill("项目根目录", setup.project_root || "")}
    </div>
    <div class="two-column">
      <div>
        <h3>最小 Prompt</h3>
        <pre>${escapeHTML(setup.minimal_prompt || "")}</pre>
      </div>
      <div>
        <h3>完整配置说明</h3>
        <pre>${escapeHTML(setup.setup_prompt || "")}</pre>
      </div>
    </div>
    <details>
      <summary>memory.json 示例</summary>
      <pre>${escapeHTML(JSON.stringify(setup.memory_json_example || {}, null, 2))}</pre>
    </details>
  </div>`;
}

function renderAgentSetupVerify(setup, status, recent) {
  const box = $("agent-setup-verify");
  if (!box) return;
  const challenge = appState.projectMemoryChallenge || {};
  box.innerHTML = challenge.instruction
    ? `<h3>复制给工作 Agent 的验证指令</h3><pre>${escapeHTML(challenge.instruction)}</pre>`
    : '<p class="muted">点击“生成验证指令”，复制给你的工作 AI Agent 执行。执行完成后再点击“测试连接”。</p>';
}

function renderAgentConnectionCard(connection, challenge) {
  const box = $("agent-connection-card");
  if (!box) return;
  const connected = Boolean(connection.connected);
  box.className = `connection-card ${connected ? "verified" : ""}`;
  box.innerHTML = `<div>
    <strong>${connected ? "已验证" : "未验证"}</strong>
    <p>${escapeHTML(connection.message || (challenge.challenge ? "验证指令已生成，等待工作 Agent 落盘。" : "还没有生成验证指令。"))}</p>
    <div class="mini-row">
      <span>Agent：${escapeHTML((appState.agentSetup || {}).display_name || "未选择")}</span>
      <span>验证码：${escapeHTML(challenge.challenge || connection.challenge || "未生成")}</span>
      <span>Review：${escapeHTML(connection.review_id || "未检测")}</span>
    </div>
    ${connection.draft_path ? `<code>${escapeHTML(connection.draft_path)}</code>` : ""}
  </div>`;
}

function projectMemoryCard(item) {
  return `<article class="capability-card ready">
    <div class="card-head">
      <div>
        <strong>${escapeHTML(item.title || "未命名项目记忆")}</strong>
        <small>${escapeHTML(item.project || "")}</small>
      </div>
      ${badge(`score ${item.score ?? 0}`, "neutral")}
    </div>
    <p>${escapeHTML(item.snippet || "")}</p>
    <div class="mini-row">
      <span>${escapeHTML(item.vault_relative_path || item.path || "")}</span>
    </div>
  </article>`;
}

function renderProjectMemoryResults(id, items) {
  $(id).innerHTML = items && items.length
    ? `<div class="capability-card-grid">${items.map(projectMemoryCard).join("")}</div>`
    : '<p class="muted">没有找到匹配结果。</p>';
}

async function loadAgentSetup(agent) {
  const selected = agent || $("agent-setup-select")?.value || "generic";
  const feedback = $("agent-setup-feedback");
  if (feedback) feedback.textContent = "正在加载工作 Agent 配置模板…";
  try {
    appState.agentSetup = await getJSON(`/api/project-memory/agent-setup?agent=${encodeURIComponent(selected)}`);
    renderAgentSetup(appState.agentSetup);
    renderAgentSetupVerify(appState.agentSetup, appState.projectMemory.status || {}, appState.projectMemory.recent || []);
    if (feedback) feedback.textContent = `已加载 ${appState.agentSetup.display_name || selected} 配置模板。`;
    return appState.agentSetup;
  } catch (error) {
    if (feedback) feedback.textContent = `加载失败：${error}`;
    appState.agentSetup = {};
    renderAgentSetup(appState.agentSetup);
    throw error;
  }
}

async function generateProjectMemoryChallenge() {
  const agent = $("agent-setup-select")?.value || "generic";
  const feedback = $("agent-setup-feedback");
  if (feedback) feedback.textContent = "正在生成真实连接验证指令…";
  appState.projectMemoryChallenge = await getJSON("/api/project-memory/connection-challenge", {
    method: "POST",
    body: JSON.stringify({ agent }),
  });
  appState.projectMemoryConnection = {};
  if (appState.projectMemoryChallenge?.instruction) {
    appState.agentSetup = {
      ...(appState.agentSetup || {}),
      challenge_instruction: appState.projectMemoryChallenge.instruction,
    };
  }
  renderAgentSetupVerify(appState.agentSetup || {}, appState.projectMemory.status || {}, appState.projectMemory.recent || []);
  renderAgentConnectionCard(appState.projectMemoryConnection, appState.projectMemoryChallenge);
  if (feedback) feedback.textContent = "验证指令已生成，请复制给工作 Agent 执行。";
  return appState.projectMemoryChallenge;
}

async function verifyProjectMemoryConnection() {
  const agent = $("agent-setup-select")?.value || "generic";
  const challenge = appState.projectMemoryChallenge?.challenge || appState.projectMemoryConnection?.challenge || "";
  const feedback = $("agent-setup-feedback");
  if (!challenge) {
    alert("请先生成验证指令。");
    return;
  }
  if (feedback) feedback.textContent = "正在扫描 _待审核 与 Review 记录…";
  appState.projectMemoryConnection = await getJSON("/api/project-memory/verify-connection", {
    method: "POST",
    body: JSON.stringify({ agent, challenge }),
  });
  renderAgentConnectionCard(appState.projectMemoryConnection, appState.projectMemoryChallenge);
  if (feedback) feedback.textContent = appState.projectMemoryConnection.connected ? "连接验证通过。" : "还没有检测到验证草稿。";
  await refreshProjectMemoryOnly();
}

async function refreshProjectMemoryOnly() {
  try {
    appState.projectMemory = await getJSON("/api/project-memory");
    renderProjectMemory();
  } catch {
    // Keep current view.
  }
}

async function ensureAgentSetupLoaded() {
  const selected = $("agent-setup-select")?.value || "generic";
  if (appState.agentSetup?.success && appState.agentSetup.agent === selected) {
    return appState.agentSetup;
  }
  return loadAgentSetup(selected);
}

function renderSystemInfo() {
  const status = appState.status || {};
  $("system-info").innerHTML = [
    pill("项目根目录", status.project_root || ""),
    pill("配置文件", status.config_path || ""),
    pill("输出目录", status.output?.folder || "未配置"),
    pill("Web Console", "127.0.0.1 本地服务"),
  ].join("");
}

function renderManifestSummary() {
  const inventory = appState.capabilities.inventory || {};
  $("manifest-summary").innerHTML = `<div class="tag-list">
    ${(inventory.source_adapters || []).map((item) => `<span>${escapeHTML(label(SOURCE_LABELS, item) || item)}</span>`).join("")}
    ${(inventory.downloader_backends || []).map((item) => `<span>${escapeHTML(label(BACKEND_LABELS, item) || item)}</span>`).join("")}
    ${(inventory.ui_surfaces || []).map((item) => `<span>${item === "web_console" ? "Web Console" : escapeHTML(item)}</span>`).join("")}
  </div>`;
}

function formObject(form) {
  const data = new FormData(form);
  const payload = {};
  for (const [key, value] of data.entries()) {
    payload[key] = value;
  }
  for (const checkbox of form.querySelectorAll("input[type=checkbox]")) {
    payload[checkbox.name] = checkbox.checked;
  }
  return payload;
}

function renderLayers(payload) {
  const layers = ["source", "acquisition", "processing", "knowledge", "delivery"];
  $("ingest-layers").innerHTML = `<div class="layers">${layers.map(layer => {
    const item = payload[layer] || {};
    const failed = item.status === "failed" || item.error || item.error_code;
    return `<div class="layer">
      <strong>${label(LAYER_LABELS, layer)}</strong>
      <div class="${failed ? "bad" : "ok"}">${label(STATUS_LABELS, item.status) || (failed ? "失败" : "正常")}</div>
      <small>${escapeHTML(item.error_code || "")}</small>
    </div>`;
  }).join("")}</div>`;
}

function renderInitNextStep(result) {
  if (!result || result.success === false) {
    $("init-next-step").textContent = "初始化未完成。请根据错误信息修正输入后重试。";
    return;
  }
  if (result.content_mode === "original" || result.mcp_setup_status === "skipped") {
    $("init-next-step").textContent = "下一步：可以直接使用 ingest / Web Console 处理内容；当前为原文模式，不需要 MCP 审核。";
    return;
  }
  $("init-next-step").textContent = "下一步：请继续完成 MCP 配置与验证，然后再使用 card / both 知识卡片流程。";
}

async function loadReviews() {
  const payload = await getJSON("/api/reviews");
  appState.reviews = payload;
  const items = payload.items || payload.reviews || [];
  $("reviews").innerHTML = items.length
    ? items.map((item) => `<div class="review-item">
        <strong>${escapeHTML(item.review_id || item.id || "")}</strong>
        <span>${escapeHTML(item.status || "")}</span>
      </div>`).join("")
    : '<p class="muted">暂无待审核记录。</p>';
}

function initSettingsControls() {
  const engineSelect = $("asr-engine-select");
  const syncAsrBlocks = () => {
    const selected = engineSelect?.value || "mimo";
    document.querySelectorAll("[data-asr-config]").forEach((block) => {
      block.hidden = block.dataset.asrConfig !== selected;
    });
  };
  engineSelect?.addEventListener("change", syncAsrBlocks);
  syncAsrBlocks();

  $("agent-setup-select")?.addEventListener("change", async (event) => {
    appState.projectMemoryChallenge = {};
    appState.projectMemoryConnection = {};
    await loadAgentSetup(event.target.value);
    renderAgentConnectionCard(appState.projectMemoryConnection, appState.projectMemoryChallenge);
  });

  document.querySelectorAll("[data-choice-group]").forEach((button) => {
    button.addEventListener("click", () => {
      const group = button.dataset.choiceGroup;
      const value = button.dataset.choiceValue;
      const input = document.querySelector(`input[name="${group}"]`);
      if (input) input.value = value;
      document.querySelectorAll(`[data-choice-group="${group}"]`).forEach((peer) => {
        peer.classList.toggle("selected", peer === button);
      });
    });
  });

  document.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.dataset.pickFolder) {
      const input = document.querySelector(`input[name="${target.dataset.pickFolder}"]`);
      if (!input) return;
      try {
        const result = await getJSON("/api/select-directory", { method: "POST", body: "{}" });
        if (result.success && result.path) {
          input.value = result.path;
          return;
        }
      } catch {
        // fall back to browser/manual picker
      }
      if ("showDirectoryPicker" in window) {
        try {
          const handle = await window.showDirectoryPicker();
          input.value = handle.name;
        } catch {
          // user cancelled
        }
      } else {
        alert("当前浏览器不支持直接选择本地文件夹，请手动粘贴目录路径。");
      }
    }
    if (target.dataset.pickFile) {
      const input = document.querySelector(`input[name="${target.dataset.pickFile}"]`);
      if (!input) return;
      try {
        const result = await getJSON("/api/select-file", { method: "POST", body: "{}" });
        if (result.success && result.path) {
          input.value = result.path;
          return;
        }
      } catch {
        // fall back to browser/manual picker
      }
      if ("showOpenFilePicker" in window) {
        try {
          const [handle] = await window.showOpenFilePicker();
          input.value = handle.name;
        } catch {
          // user cancelled
        }
      } else {
        alert("当前浏览器不支持直接选择 Cookie 文件，请手动粘贴文件路径。");
      }
    }
    if (target.dataset.configCookie) {
      renderCookiePanel(target.dataset.configCookie);
    }
    if (target.dataset.copyAgentSetup) {
      const key = target.dataset.copyAgentSetup;
      if (key === "challenge_instruction" && !appState.projectMemoryChallenge?.instruction) {
        await generateProjectMemoryChallenge();
      }
      const setup = key === "challenge_instruction"
        ? { challenge_instruction: appState.projectMemoryChallenge?.instruction }
        : await ensureAgentSetupLoaded();
      const value = setup?.[key];
      if (value === undefined) {
        alert("当前没有可复制内容，请先选择工作 Agent。");
        return;
      }
      const ok = await copyText(value);
      const feedback = $("agent-setup-feedback");
      if (feedback) feedback.textContent = ok ? "已复制到剪贴板。" : "复制失败，请手动选中文本复制。";
      target.textContent = ok ? "已复制" : "复制失败";
      setTimeout(() => {
        const labels = {
          setup_prompt: "复制完整配置说明",
          minimal_prompt: "复制最小 Prompt",
          status_command: "复制验证命令",
          memory_json_example: "复制 memory.json 示例",
          challenge_instruction: "复制验证指令",
        };
        target.textContent = labels[key] || "复制";
      }, 1500);
    }
    if (target.id === "generate-agent-challenge") {
      await generateProjectMemoryChallenge();
    }
    if (target.id === "verify-agent-connection") {
      await verifyProjectMemoryConnection();
    }
    if (target.dataset.openLogin) {
      if (target.dataset.openLogin) {
        window.open(target.dataset.openLogin, "_blank", "noopener,noreferrer");
      }
    }
    if (target.id === "prepare-cookie-config") {
      const form = $("source-settings-form");
      const browser = form?.querySelector('select[name="cookies_from_browser"]')?.value;
      const flow = $("cookie-flow-state");
      if (!browser) {
        alert("请先选择一个浏览器，例如 Microsoft Edge 或 Chrome。");
        return;
      }
      form.querySelector('input[name="cookie_ready"]').value = "true";
      flow.classList.add("ready");
      flow.querySelector("strong").textContent = "浏览器 Cookie 来源已选择";
      flow.querySelector("p").textContent = "保存后，yt-dlp 会在获取内容时按官方 --cookies-from-browser 方式读取该浏览器登录态；系统不会导出或展示 Cookie 内容。";
    }
    if (target.id === "close-source-settings") {
      $("source-settings-panel").innerHTML = "";
    }
  });
}

window.addEventListener("hashchange", () => setRoute(currentRoute()));
$("refresh").addEventListener("click", refreshAll);
$("load-reviews").addEventListener("click", loadReviews);

$("init-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formObject(event.currentTarget);
  payload.configure_mcp = Boolean(payload.configure_mcp);
  payload.keep_audio = payload.keep_audio === true || payload.keep_audio === "true";
  const result = await getJSON("/api/init-config", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderInitNextStep(result);
  renderJSON("init-result", result);
  await refreshAll();
});

$("ingest-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formObject(event.currentTarget);
  const result = await getJSON("/api/ingest", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  appState.lastIngest = result;
  renderLayers(result);
  renderJSON("ingest-result", result);
  renderDashboard();
  renderDeliveryPreview();
});

$("project-memory-search-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formObject(event.currentTarget);
  const params = new URLSearchParams({
    q: payload.query || "",
    project: payload.project || "",
    limit: "20",
  });
  const result = await getJSON(`/api/project-memory/search?${params.toString()}`);
  renderProjectMemoryResults("project-memory-search-results", result.results || []);
});

$("project-memory-match-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formObject(event.currentTarget);
  const result = await getJSON("/api/project-memory/match", {
    method: "POST",
    body: JSON.stringify({ idea: payload.idea || "", limit: 5 }),
  });
  const items = (result.candidates || []).map((item) => ({
    ...item,
    snippet: item.reason || item.suggested_action || "",
  }));
  renderProjectMemoryResults("project-memory-match-results", items);
});

document.addEventListener("submit", async (event) => {
  if (event.target?.id !== "source-settings-form") return;
  event.preventDefault();
  const payload = formObject(event.target);
  if (payload.cookies_from_browser && payload.cookie_ready !== "true") {
    alert("请先点击“我已登录，使用该浏览器 Cookie 来源”，确认状态变蓝后再保存。");
    return;
  }
  delete payload.cookie_ready;
  const result = await getJSON("/api/source-settings", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  $("source-settings-result").textContent = JSON.stringify(result, null, 2);
  await refreshAll();
});

initSettingsControls();
setRoute(currentRoute());
refreshAll().catch((error) => {
  $("dashboard-notice").textContent = `加载失败：${error}`;
});
