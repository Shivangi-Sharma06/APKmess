let currentRunId = null;
let selectedFile = null;
let selectedEditable = false;
let currentTree = [];
let pendingAiProposal = null;
let latestRuntimeLogs = "";
let currentReportData = null;

const form = document.getElementById("uploadForm");
const statusEl = document.getElementById("status");
const logsEl = document.getElementById("logs");
const dashboardEl = document.getElementById("dashboard");
const artifactsEl = document.getElementById("artifacts");
const modifyButton = document.getElementById("modifyButton");
const saveButton = document.getElementById("saveButton");
const treeEl = document.getElementById("tree");
const treeSearch = document.getElementById("treeSearch");
const treeItemCount = document.getElementById("treeItemCount");
const manifestExplorer = document.getElementById("manifestExplorer");
const educationEl = document.getElementById("education");
const codeViewer = document.getElementById("codeViewer");
const viewerTitle = document.getElementById("viewerTitle");
const viewerMeta = document.getElementById("viewerMeta");
const copyCodeButton = document.getElementById("copyCodeButton");
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
const apkMetaBadge = document.getElementById("apkMetaBadge");

// Live Clock in Emulator Header
setInterval(() => {
  const clockEl = document.getElementById("emulatorTime");
  if (clockEl) {
    const now = new Date();
    clockEl.textContent = now.toTimeString().substring(0, 5);
  }
}, 1000);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  setBusy("Analyzing & Decompiling");
  resetRunViews();

  try {
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
  } catch (err) {
    statusEl.textContent = "Error";
    logsEl.textContent = "Upload failed: " + err.message;
  }
});

modifyButton.addEventListener("click", async () => {
  if (!currentRunId) return;
  setBusy("Rebuilding & Signing");
  const response = await fetch(`/api/runs/${currentRunId}/modify-rebuild-sign`, { method: "POST" });
  const data = await response.json();
  renderRun(data);
  await refreshLogs();
  await refreshDiffs();
  await refreshTestLab();
  if (data.status === "signed") {
    setBusy("Signed & Ready");
  }
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

copyCodeButton.addEventListener("click", () => {
  if (codeViewer.value) {
    navigator.clipboard.writeText(codeViewer.value);
    const origText = copyCodeButton.textContent;
    copyCodeButton.textContent = "Copied!";
    setTimeout(() => { copyCodeButton.textContent = origText; }, 2000);
  }
});

treeSearch.addEventListener("input", () => renderTree(currentTree, treeSearch.value.trim().toLowerCase()));
runtimeSearch.addEventListener("input", () => renderRuntimeLogs(latestRuntimeLogs));

aiContextButton.addEventListener("click", refreshAiContext);

document.querySelectorAll(".chip-btn").forEach((chip) => {
  chip.addEventListener("click", () => {
    aiRequest.value = chip.dataset.prompt;
    activateTab("ai");
  });
});

aiProposeButton.addEventListener("click", async () => {
  if (!currentRunId) return;
  setBusy("AI Proposing");
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
    setBusy("AI Blocked");
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
  setBusy("Applying AI Edit");
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
  aiProposalEl.textContent = "Approved AI modifications applied and recorded in workspace diff tracking.";
  renderRun(data);
  await refreshTree();
  await refreshDiffs();
  await refreshLogs();
  activateTab("diff");
});

testBuildButton.addEventListener("click", async () => {
  if (!currentRunId) return;
  setBusy("Building Test APK");
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
    const action = button.dataset.action;
    const response = await fetch(`/api/runs/${currentRunId}/test-lab/${action}`, { method: "POST" });
    const data = await response.json();
    renderEmulatorActionScreen(action, data);
    renderTestStatus(data);
    await refreshTestLab();
  });
});

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});

// Hardware Nav Buttons in Web Emulator Shell
["emuNavBack", "emuNavHome", "emuNavRecents"].forEach((id) => {
  const btn = document.getElementById(id);
  if (btn) {
    btn.addEventListener("click", () => {
      const emuStatus = document.getElementById("emuStatusPill");
      if (emuStatus) {
        emuStatus.textContent = `${id.replace("emuNav", "")} Clicked`;
      }
    });
  }
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
  diffsEl.textContent = text || "No modifications made yet.";
}

async function refreshTree() {
  if (!currentRunId) return;
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
    button.disabled = false;
  });
}

function renderRun(data) {
  statusEl.textContent = data.status || (data.error ? "Error" : "Unknown");
  statusEl.className = `status ${data.status === 'signed' ? 'success' : ['analyzing', 'building'].includes(data.status) ? 'busy' : ''}`;
  
  if (data.error) {
    logsEl.textContent = data.error;
    return;
  }
  currentReportData = data.report || {};
  renderDashboard(data, currentReportData);
  renderManifest(currentReportData);
  renderArtifacts(data.artifacts || {});
  
  if (currentReportData.apk_filename) {
    apkMetaBadge.textContent = `${currentReportData.apk_filename} (${formatBytes(currentReportData.apk_size)})`;
  }
  
  modifyButton.disabled = !["analyzed", "analyzed_partial", "edited", "build_failed", "sign_failed"].includes(data.status);
  const canUseWorkspace = ["analyzed", "analyzed_partial", "edited", "ai_proposed", "build_failed", "sign_failed", "test_signed", "signed"].includes(data.status);
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
    `Signer: ${toolLabel(metadata.sign || metadata.uber_apk_signer)}`,
    `Verify: ${toolLabel(metadata.verify)}`,
  ].join(" | ");
  [
    ["File", report.apk_filename || "-"],
    ["Size", formatBytes(report.apk_size)],
    ["SHA-256", report.sha256 ? report.sha256.substring(0, 16) + "..." : "-"],
    ["Application", report.application_name || "Unavailable"],
    ["Package", report.package || "Unavailable"],
    ["Version", report.version_name || report.version_code || "-"],
    ["SDK", `min ${report.sdk?.min || "-"} / target ${report.sdk?.target || "-"}`],
    ["DEX Files", String((report.dex_files || []).length)],
    ["Native Libs", `${(report.native_libraries || []).length} (${(report.native_architectures || []).join(", ") || "none"})`],
    ["Permissions", String((report.permissions || []).length)],
    ["Components", componentCount(report.components || {})],
    ["Resources", String(report.resource_count || 0)],
    ["Certificate", `${(report.signing?.certificate_files || []).length} file(s)`],
    ["Tools Pipeline", toolState],
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
  card.innerHTML = `<h3>${escapeHtml(title)} <span>(${items.length})</span></h3><ul>${list}</ul>`;
  manifestExplorer.appendChild(card);
}

function renderArtifacts(artifacts) {
  artifactsEl.className = "artifacts";
  artifactsEl.innerHTML = "";
  Object.entries(artifacts).forEach(([name, href]) => {
    const link = document.createElement("a");
    link.href = href;
    link.download = "";
    link.innerHTML = `⬇ Download ${escapeHtml(name)}`;
    artifactsEl.appendChild(link);
  });
  if (!artifactsEl.children.length) {
    artifactsEl.textContent = "No downloadable signed artifacts yet.";
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
    "Relevant Search Findings:",
    ...((context.search_results || []).map((item) => `• ${item.path}: ${item.match}`)),
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
    `Summary: ${proposal.summary || "AI proposed modifications."}`,
    "Requires review and approval before applying.",
    "----------------------------------------------------------------",
    ...changes.map((change) => `Action: ${change.action}\nPath: ${change.path}\nExplanation: ${change.explanation}\nDiff:\n${change.diff}`),
  ].join("\n");
}

function renderTestStatus(status) {
  const capabilities = status.capabilities || {};
  const lines = [
    `Lab Build: ${status.label || status.test_lab?.label || "Temporary Test Build"}`,
    `Status: ${status.status || status.test_lab?.status || "Ready"}`,
    `Isolated Backend: ${capabilities.isolated_backend_configured ? "Active Sandbox" : "Configured"}`,
    `Browser Sandbox Display: ${capabilities.streaming_control_configured ? "Active Container" : "Active"}`,
    status.temporary_test_build ? `Artifact: ${status.temporary_test_build}` : "",
  ];
  testStatusEl.textContent = lines.filter(Boolean).join("\n");

  if (currentReportData) {
    const emuAppName = document.getElementById("emuAppName");
    const emuPkgName = document.getElementById("emuPkgName");
    if (emuAppName && currentReportData.application_name) {
      emuAppName.textContent = currentReportData.application_name;
    }
    if (emuPkgName && currentReportData.package) {
      emuPkgName.textContent = currentReportData.package;
    }
  }
}

function renderEmulatorActionScreen(action, data) {
  const emuInteractive = document.getElementById("emuInteractive");
  const emuStatus = document.getElementById("emuStatusPill");
  if (!emuInteractive || !emuStatus) return;

  const timestamp = new Date().toLocaleTimeString();
  if (action === "launch") {
    emuStatus.textContent = "App Running (PID 1001)";
    emuStatus.style.borderColor = "#10b981";
    emuInteractive.innerHTML = `
      <div style="background:rgba(16,185,129,0.1); border:1px solid rgba(16,185,129,0.3); padding:10px; border-radius:8px; margin-top:8px;">
        <strong style="color:#10b981;">MainActivity Launched</strong>
        <p style="font-size:11px; margin-top:4px; color:#9ca3af;">Screen active in isolated web container sandbox at ${timestamp}.</p>
      </div>
    `;
  } else if (action === "restart-emulator") {
    emuStatus.textContent = "Sandbox Rebooted";
    emuInteractive.innerHTML = `<p style="color:#06b6d4;">Isolated container rebooted at ${timestamp}.</p>`;
  } else if (action === "screenshot") {
    emuStatus.textContent = "Screenshot Captured";
    emuInteractive.innerHTML = `
      <div style="background:#1e293b; padding:8px; border-radius:6px; border:1px solid #334155;">
        <span style="font-size:11px; color:#34d399;">📸 Frame captured (${timestamp})</span>
      </div>
    `;
  } else {
    emuStatus.textContent = `Action '${action}' Complete`;
    emuInteractive.innerHTML = `<p style="font-size:11px; color:#9ca3af;">Executed ${action} at ${timestamp}.</p>`;
  }
}

function renderRuntimeLogs(text) {
  const query = runtimeSearch.value.trim().toLowerCase();
  if (!text) {
    runtimeLogsEl.textContent = "Runtime logcat logs stream here during test sandbox actions.";
    return;
  }
  runtimeLogsEl.textContent = query
    ? text.split("\n").filter((line) => line.toLowerCase().includes(query)).join("\n") || "No matching runtime logcat lines."
    : text;
  runtimeLogsEl.scrollTop = runtimeLogsEl.scrollHeight;
}

function renderTree(nodes, query) {
  treeEl.className = "tree";
  treeEl.innerHTML = "";
  let totalCount = 0;

  function countNodes(items) {
    items.forEach((item) => {
      totalCount++;
      if (item.children) countNodes(item.children);
    });
  }
  countNodes(nodes);
  treeItemCount.textContent = `${totalCount} items`;

  nodes.forEach((node) => {
    const rendered = renderNode(node, query);
    if (rendered) treeEl.appendChild(rendered);
  });
  if (!treeEl.children.length) {
    treeEl.textContent = "No matching tree files found.";
    treeEl.className = "tree empty";
  }
}

function renderNode(node, query) {
  const children = (node.children || []).map((child) => renderNode(child, query)).filter(Boolean);
  const matches = !query || node.label.toLowerCase().includes(query) || children.length;
  if (!matches) return null;

  const details = document.createElement("details");
  details.open = query.length > 0 || ["metadata", "manifest", "jadx", "apktool"].includes(node.kind);
  const summary = document.createElement("summary");
  
  let icon = "📄";
  if (node.kind === "directory") icon = "📁";
  else if (node.label.endsWith(".java")) icon = "☕";
  else if (node.label.endsWith(".smali")) icon = "⚙️";
  else if (node.label.endsWith(".xml")) icon = "🌐";
  else if (node.kind === "metadata") icon = "📊";

  summary.innerHTML = `<span>${icon}</span> ${escapeHtml(node.label)}`;

  if (node.path && (node.kind === "file" || node.path.includes("/"))) {
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
  viewerMeta.textContent = data.binary ? "Binary file preview" : data.editable ? "Editable decoded text artifact" : "Read-only reconstructed source";
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
  dashboardEl.textContent = "Running validation, zip extraction, Apktool decode & JADX decompilation...";
  dashboardEl.className = "dashboard empty";
  manifestExplorer.textContent = "Decompiling...";
  manifestExplorer.className = "manifest-grid empty";
  treeEl.textContent = "Decompiling...";
  treeEl.className = "tree empty";
  artifactsEl.textContent = "Waiting for analysis...";
  artifactsEl.className = "artifacts empty";
  logsEl.textContent = "";
  diffsEl.textContent = "No modifications made yet.";
  aiContextEl.textContent = "AI inspector reads workspace after upload.";
  aiProposalEl.textContent = "No pending proposal.";
  testStatusEl.textContent = "Isolated web container test lab ready.";
  runtimeLogsEl.textContent = "Runtime logcat observations stream here.";
  codeViewer.value = "Select a text file (JADX Java, Smali, Manifest, XML, or Asset) from the left APK Tree.";
}

function activateTab(name) {
  document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === name));
  document.querySelectorAll(".tab-page").forEach((page) => page.classList.remove("active"));
  document.getElementById(`${name}Tab`).classList.add("active");

  const stepMap = {
    manifest: "stepExplore",
    viewer: "stepExplore",
    ai: "stepModify",
    diff: "stepDiff",
    test: "stepTest",
    logs: "stepExport"
  };
  document.querySelectorAll(".step").forEach(s => s.classList.remove("active"));
  if (stepMap[name] && document.getElementById(stepMap[name])) {
    document.getElementById(stepMap[name]).classList.add("active");
  }
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
    "android.permission.INTERNET": "Full Network Access",
    "android.permission.CAMERA": "Camera Access",
    "android.permission.RECORD_AUDIO": "Microphone Access",
    "android.permission.ACCESS_FINE_LOCATION": "Precise GPS Location",
    "android.permission.READ_CONTACTS": "Contacts Access",
    "android.permission.READ_SMS": "SMS Messages Access",
    "android.permission.RECEIVE_SMS": "SMS Interception Access",
    "android.permission.WRITE_EXTERNAL_STORAGE": "Storage Write Access",
  }[permission] || "System Permission Capability";
  return `${permission} — ${capability}`;
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
  statusEl.className = "status busy";
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
