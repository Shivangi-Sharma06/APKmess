let currentRunId = null;
let selectedFile = null;
let selectedEditable = false;
let currentTree = [];
let pendingAiProposal = null;
let latestRuntimeLogs = "";

const form = document.getElementById("uploadForm");
const statusEl = document.getElementById("status");
const logsEl = document.getElementById("logs");
const dashboardEl = document.getElementById("dashboard");
const artifactsEl = document.getElementById("artifacts");
const modifyButton = document.getElementById("modifyButton");
const saveButton = document.getElementById("saveButton");
const treeEl = document.getElementById("tree");
const treeSearch = document.getElementById("treeSearch");
const manifestExplorer = document.getElementById("manifestExplorer");
const educationEl = document.getElementById("education");
const codeViewer = document.getElementById("codeViewer");
const viewerTitle = document.getElementById("viewerTitle");
const viewerMeta = document.getElementById("viewerMeta");
const diffsEl = document.getElementById("diffs");
const aiRequest = document.getElementById("aiRequest");
const aiContextButton = document.getElementById("aiContextButton");
const aiProposeButton = document.getElementById("aiProposeButton");
const aiApplyButton = document.getElementById("aiApplyButton");
const aiContextEl = document.getElementById("aiContext");
const aiProposalEl = document.getElementById("aiProposal");
const testBuildButton = document.getElementById("testBuildButton");
const testStatusEl = document.getElementById("testStatus");
const runtimeLogsEl = document.getElementById("runtimeLogs");
const runtimeSearch = document.getElementById("runtimeSearch");
const emulatorView = document.getElementById("emulatorView");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  setBusy("Analyzing");
  resetRunViews();

  const response = await fetch("/api/runs", { method: "POST", body: formData });
  const data = await response.json();
  currentRunId = data.run_id || null;
  renderRun(data);
  if (currentRunId) {
    await refreshTree();
    await refreshLogs();
    await refreshAiContext();
    await refreshTestLab();
  }
});

modifyButton.addEventListener("click", async () => {
  if (!currentRunId) return;
  setBusy("Building");
  const response = await fetch(`/api/runs/${currentRunId}/modify-rebuild-sign`, { method: "POST" });
  const data = await response.json();
  renderRun(data);
  await refreshLogs();
  await refreshDiffs();
  await refreshTestLab();
});

saveButton.addEventListener("click", async () => {
  if (!currentRunId || !selectedFile || !selectedEditable) return;
  const response = await fetch(`/api/runs/${currentRunId}/file`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: selectedFile, content: codeViewer.value }),
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.error || "Save failed");
    return;
  }
  renderRun(data);
  await refreshDiffs();
  await refreshLogs();
  await refreshTree();
  await refreshAiContext();
  setBusy("Edited");
});

treeSearch.addEventListener("input", () => renderTree(currentTree, treeSearch.value.trim().toLowerCase()));
runtimeSearch.addEventListener("input", () => renderRuntimeLogs(latestRuntimeLogs));

aiContextButton.addEventListener("click", refreshAiContext);

aiProposeButton.addEventListener("click", async () => {
  if (!currentRunId) return;
  setBusy("AI inspecting");
  const response = await fetch(`/api/runs/${currentRunId}/ai/propose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request: aiRequest.value }),
  });
  const data = await response.json();
  if (!response.ok) {
    aiProposalEl.textContent = data.error || "AI proposal failed.";
    aiApplyButton.disabled = true;
    pendingAiProposal = null;
    setBusy("AI blocked");
    return;
  }
  pendingAiProposal = data;
  renderAiProposal(data);
  renderAiContext(data.observations || {});
  aiApplyButton.disabled = !(data.changes || []).length;
  statusEl.textContent = "ai_proposed";
  await refreshLogs();
});

aiApplyButton.addEventListener("click", async () => {
  if (!currentRunId || !pendingAiProposal) return;
  setBusy("Applying AI edit");
  const response = await fetch(`/api/runs/${currentRunId}/ai/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved: true }),
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.error || "AI apply failed");
    return;
  }
  pendingAiProposal = null;
  aiApplyButton.disabled = true;
  aiProposalEl.textContent = "Approved AI changes were applied and recorded in shared modification history.";
  renderRun(data);
  await refreshTree();
  await refreshDiffs();
  await refreshLogs();
  activateTab("diff");
});

testBuildButton.addEventListener("click", async () => {
  if (!currentRunId) return;
  setBusy("Test build");
  const response = await fetch(`/api/runs/${currentRunId}/test-lab/build`, { method: "POST" });
  const data = await response.json();
  renderRun(data);
  renderTestStatus(data.test_lab || data);
  await refreshLogs();
  await refreshTestLab();
});

document.querySelectorAll(".test-action").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!currentRunId) return;
    const response = await fetch(`/api/runs/${currentRunId}/test-lab/${button.dataset.action}`, { method: "POST" });
    const data = await response.json();
    renderTestStatus(data);
    await refreshTestLab();
  });
});

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});

async function refreshLogs() {
  if (!currentRunId) return;
  const response = await fetch(`/api/runs/${currentRunId}/logs`);
  logsEl.textContent = await response.text();
  logsEl.scrollTop = logsEl.scrollHeight;
}

async function refreshDiffs() {
  if (!currentRunId) return;
  const response = await fetch(`/api/runs/${currentRunId}/diff`);
  const text = await response.text();
  diffsEl.textContent = text || "No modifications yet.";
}

async function refreshTree() {
  const response = await fetch(`/api/runs/${currentRunId}/tree`);
  const data = await response.json();
  currentTree = data.tree || [];
  renderTree(currentTree, "");
}

async function refreshAiContext() {
  if (!currentRunId) return;
  const response = await fetch(`/api/runs/${currentRunId}/ai/context?q=${encodeURIComponent(aiRequest.value)}`);
  const data = await response.json();
  if (response.ok) renderAiContext(data);
  aiContextButton.disabled = false;
  aiProposeButton.disabled = false;
}

async function refreshTestLab() {
  if (!currentRunId) return;
  const response = await fetch(`/api/runs/${currentRunId}/test-lab`);
  const data = await response.json();
  if (!response.ok) return;
  renderTestStatus(data);
  latestRuntimeLogs = data.observations?.logs || "";
  renderRuntimeLogs(latestRuntimeLogs);
  testBuildButton.disabled = false;
  document.querySelectorAll(".test-action").forEach((button) => {
    button.disabled = !data.has_temporary_test_build;
  });
}

function renderRun(data) {
  statusEl.textContent = data.status || (data.error ? "Error" : "Unknown");
  if (data.error) {
    logsEl.textContent = data.error;
    return;
  }
  const report = data.report || {};
  renderDashboard(data, report);
  renderManifest(report);
  renderArtifacts(data.artifacts || {});
  modifyButton.disabled = !["analyzed", "analyzed_partial", "edited", "build_failed", "sign_failed"].includes(data.status);
  const canUseWorkspace = ["analyzed", "analyzed_partial", "edited", "ai_proposed", "build_failed", "sign_failed", "test_signed"].includes(data.status);
  aiContextButton.disabled = !canUseWorkspace;
  aiProposeButton.disabled = !canUseWorkspace;
  testBuildButton.disabled = !canUseWorkspace;
}

function renderDashboard(data, report) {
  dashboardEl.className = "dashboard";
  dashboardEl.innerHTML = "";
  const metadata = data.metadata || {};
  const toolState = [
    `Apktool: ${toolLabel(metadata.apktool)}`,
    `JADX: ${toolLabel(metadata.jadx)}`,
    `Zipalign: ${toolLabel(metadata.align)}`,
    `Uber signer: ${toolLabel(metadata.uber_apk_signer)}`,
    `Verify: ${toolLabel(metadata.verify)}`,
  ].join(" | ");
  [
    ["File", report.apk_filename || "-"],
    ["Size", formatBytes(report.apk_size)],
    ["SHA-256", report.sha256 || "-"],
    ["Application", report.application_name || "Unavailable"],
    ["Package", report.package || "Unavailable"],
    ["Version", report.version_name || report.version_code || "-"],
    ["SDK", `min ${report.sdk?.min || "-"} / target ${report.sdk?.target || "-"}`],
    ["DEX files", String((report.dex_files || []).length)],
    ["Native libraries", `${(report.native_libraries || []).length} (${(report.native_architectures || []).join(", ") || "none"})`],
    ["Permissions", String((report.permissions || []).length)],
    ["Components", componentCount(report.components || {})],
    ["Resources", String(report.resource_count || 0)],
    ["Signing", `${(report.signing?.certificate_files || []).length} certificate file(s)`],
    ["Tool status", toolState],
  ].forEach(([label, value]) => addMetric(dashboardEl, label, value));
}

function renderManifest(report) {
  const components = report.components || {};
  manifestExplorer.className = "manifest-grid";
  manifestExplorer.innerHTML = "";
  addManifestCard("Permissions", report.permissions || [], permissionExplain);
  addManifestCard("Activities", components.activities || [], componentExplain);
  addManifestCard("Services", components.services || [], componentExplain);
  addManifestCard("Receivers", components.receivers || [], componentExplain);
  addManifestCard("Providers", components.providers || [], componentExplain);
  addManifestCard("Intent Filters", report.intent_filters || [], intentExplain);

  educationEl.innerHTML = "";
  Object.entries(report.education || {}).forEach(([label, value]) => addMetric(educationEl, label.replaceAll("_", " "), value));
}

function addManifestCard(title, items, explain) {
  const card = document.createElement("div");
  card.className = "manifest-card";
  const list = items.length ? items.map((item) => `<li>${escapeHtml(explain(item))}</li>`).join("") : "<li>None detected or unavailable.</li>";
  card.innerHTML = `<h3>${escapeHtml(title)} <span>${items.length}</span></h3><ul>${list}</ul>`;
  manifestExplorer.appendChild(card);
}

function renderArtifacts(artifacts) {
  artifactsEl.className = "artifacts";
  artifactsEl.innerHTML = "";
  Object.entries(artifacts).forEach(([name, href]) => {
    const link = document.createElement("a");
    link.href = href;
    link.textContent = name;
    artifactsEl.appendChild(link);
  });
  if (!artifactsEl.children.length) {
    artifactsEl.textContent = "No downloadable artifacts yet.";
    artifactsEl.className = "artifacts empty";
  }
}

function renderAiContext(context) {
  if (!context || !Object.keys(context).length) {
    aiContextEl.textContent = "No workspace context available yet.";
    return;
  }
  const lines = [
    `Workspace: ${context.workspace || "-"}`,
    `Package: ${context.package || "-"}`,
    `Application: ${context.application_name || "-"}`,
    `Permissions: ${(context.permissions || []).length}`,
    `Components: ${JSON.stringify(context.components || {})}`,
    `Existing modifications: ${context.existing_modifications || 0}`,
    `Implemented tools: ${(context.implemented_tools || []).join(", ")}`,
    "",
    "Relevant search results:",
    ...((context.search_results || []).map((item) => `${item.path}: ${item.match}`)),
  ];
  aiContextEl.textContent = lines.join("\n").trim();
}

function renderAiProposal(proposal) {
  const changes = proposal.changes || [];
  if (!changes.length) {
    aiProposalEl.textContent = proposal.explanation ? JSON.stringify(proposal.explanation, null, 2) : (proposal.summary || "No file changes proposed.");
    return;
  }
  aiProposalEl.textContent = [
    proposal.summary || "AI proposed changes.",
    "Requires user approval before applying.",
    "",
    ...changes.map((change) => `${change.action} ${change.path}\n${change.explanation}\n${change.diff}`),
  ].join("\n");
}

function renderTestStatus(status) {
  const capabilities = status.capabilities || {};
  const lines = [
    `Label: ${status.label || status.test_lab?.label || "Temporary Test Build"}`,
    `Status: ${status.status || status.test_lab?.status || "not built"}`,
    `Isolated emulator backend: ${capabilities.isolated_backend_configured ? "configured" : "unavailable"}`,
    `Browser stream/control: ${capabilities.streaming_control_configured ? "configured" : "unavailable"}`,
    status.temporary_test_build ? `Artifact: ${status.temporary_test_build}` : "",
    status.error ? `Error: ${status.error}` : "",
    capabilities.reason ? `Reason: ${capabilities.reason}` : "",
  ];
  testStatusEl.textContent = lines.filter(Boolean).join("\n");
  emulatorView.textContent = capabilities.available ? "Emulator stream ready." : "Isolated emulator stream unavailable.";
}

function renderRuntimeLogs(text) {
  const query = runtimeSearch.value.trim().toLowerCase();
  if (!text) {
    runtimeLogsEl.textContent = "No runtime observations for this test execution.";
    return;
  }
  runtimeLogsEl.textContent = query
    ? text.split("\n").filter((line) => line.toLowerCase().includes(query)).join("\n") || "No matching runtime log lines."
    : text;
}

function renderTree(nodes, query) {
  treeEl.className = "tree";
  treeEl.innerHTML = "";
  nodes.forEach((node) => {
    const rendered = renderNode(node, query);
    if (rendered) treeEl.appendChild(rendered);
  });
  if (!treeEl.children.length) {
    treeEl.textContent = "No matching nodes.";
    treeEl.className = "tree empty";
  }
}

function renderNode(node, query) {
  const children = (node.children || []).map((child) => renderNode(child, query)).filter(Boolean);
  const matches = !query || node.label.toLowerCase().includes(query) || children.length;
  if (!matches) return null;
  const details = document.createElement("details");
  details.open = query.length > 0 || ["metadata", "manifest"].includes(node.kind);
  const summary = document.createElement("summary");
  summary.textContent = node.label;
  if (node.path && node.kind === "file") {
    summary.className = "clickable";
    summary.addEventListener("click", (event) => {
      event.preventDefault();
      openFile(node.path);
    });
  }
  details.appendChild(summary);
  children.forEach((child) => details.appendChild(child));
  return details;
}

async function openFile(path) {
  if (!currentRunId) return;
  const response = await fetch(`/api/runs/${currentRunId}/file?path=${encodeURIComponent(path)}`);
  const data = await response.json();
  if (!response.ok) {
    alert(data.error || "Unable to open file");
    return;
  }
  selectedFile = data.path;
  selectedEditable = data.editable;
  viewerTitle.textContent = data.path;
  viewerMeta.textContent = data.binary ? "binary preview" : data.editable ? "editable decoded text" : "read-only";
  codeViewer.value = data.content;
  codeViewer.readOnly = !data.editable;
  saveButton.disabled = !data.editable;
  activateTab("viewer");
}

function resetRunViews() {
  currentRunId = null;
  selectedFile = null;
  selectedEditable = false;
  saveButton.disabled = true;
  modifyButton.disabled = true;
  aiContextButton.disabled = true;
  aiProposeButton.disabled = true;
  aiApplyButton.disabled = true;
  testBuildButton.disabled = true;
  document.querySelectorAll(".test-action").forEach((button) => {
    button.disabled = true;
  });
  pendingAiProposal = null;
  dashboardEl.textContent = "Running validation, extraction, decompilation, and analysis...";
  dashboardEl.className = "dashboard empty";
  manifestExplorer.textContent = "Working...";
  manifestExplorer.className = "manifest-grid empty";
  treeEl.textContent = "Working...";
  treeEl.className = "tree empty";
  artifactsEl.textContent = "Working...";
  artifactsEl.className = "artifacts empty";
  logsEl.textContent = "";
  diffsEl.textContent = "No modifications yet.";
  aiContextEl.textContent = "AI tools inspect the analyzed workspace after upload.";
  aiProposalEl.textContent = "No pending proposal.";
  testStatusEl.textContent = "Runtime testing is optional and requires isolated Android emulator infrastructure.";
  runtimeLogsEl.textContent = "Runtime observations appear here when an isolated emulator backend is configured.";
  codeViewer.value = "Select a text file from the tree.";
}

function activateTab(name) {
  document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === name));
  document.querySelectorAll(".tab-page").forEach((page) => page.classList.remove("active"));
  document.getElementById(`${name}Tab`).classList.add("active");
}

function addMetric(parent, label, value) {
  const item = document.createElement("div");
  item.className = "metric";
  item.innerHTML = `<b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span>`;
  parent.appendChild(item);
}

function componentCount(components) {
  return String(Object.values(components).reduce((total, items) => total + (items || []).length, 0));
}

function toolLabel(result) {
  if (!result) return "not run";
  if (result.ok) return "ok";
  if (result.skipped) return "missing";
  return `failed (${result.exit_code})`;
}

function permissionExplain(permission) {
  const capability = {
    "android.permission.INTERNET": "network access",
    "android.permission.CAMERA": "camera access",
    "android.permission.RECORD_AUDIO": "microphone access",
    "android.permission.ACCESS_FINE_LOCATION": "precise location",
    "android.permission.READ_CONTACTS": "contacts read access",
    "android.permission.READ_SMS": "SMS read access",
    "android.permission.RECEIVE_SMS": "SMS receive access",
  }[permission] || "Android capability";
  return `${permission} - ${capability}`;
}

function componentExplain(item) {
  return `${item.name || "<unnamed>"} | exported=${item.exported || "unspecified"} | permission=${item.permission || "none"}`;
}

function intentExplain(item) {
  return `${item.component || "unknown component"} | actions=${(item.actions || []).join(", ") || "none"}`;
}

function formatBytes(value) {
  if (!Number.isFinite(Number(value))) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = Number(value);
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit ? 1 : 0)} ${units[unit]}`;
}

function setBusy(label) {
  statusEl.textContent = label;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}
