let currentRunId = null;

const form = document.getElementById("uploadForm");
const statusEl = document.getElementById("status");
const logsEl = document.getElementById("logs");
const summaryEl = document.getElementById("summary");
const artifactsEl = document.getElementById("artifacts");
const modifyButton = document.getElementById("modifyButton");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  setBusy("Analyzing");
  summaryEl.textContent = "Running validation, extraction, decompilation, and analysis...";
  summaryEl.className = "summary empty";
  artifactsEl.textContent = "Working...";
  artifactsEl.className = "artifacts empty";
  logsEl.textContent = "";
  modifyButton.disabled = true;

  const response = await fetch("/api/runs", { method: "POST", body: formData });
  const data = await response.json();
  currentRunId = data.run_id || null;
  renderRun(data);
  await refreshLogs();
});

modifyButton.addEventListener("click", async () => {
  if (!currentRunId) return;
  setBusy("Rebuilding");
  const response = await fetch(`/api/runs/${currentRunId}/modify-rebuild-sign`, { method: "POST" });
  const data = await response.json();
  renderRun(data);
  await refreshLogs();
});

async function refreshLogs() {
  if (!currentRunId) return;
  const response = await fetch(`/api/runs/${currentRunId}/logs`);
  logsEl.textContent = await response.text();
  logsEl.scrollTop = logsEl.scrollHeight;
}

function renderRun(data) {
  statusEl.textContent = data.status || (data.error ? "Error" : "Unknown");
  if (data.error) {
    logsEl.textContent = data.error;
    return;
  }
  const report = data.report || {};
  summaryEl.className = "summary";
  summaryEl.innerHTML = "";
  addMetric("Run ID", data.run_id || "-");
  addMetric("Package", report.package || "Unavailable without decoded manifest");
  addMetric("Version", report.version_name || report.version_code || "-");
  addMetric("Permissions", String((report.permissions || []).length));
  addMetric("Components", componentCount(report.components || {}));
  addMetric("DEX files", String((report.dex_files || []).length));
  addMetric("URLs/domains", `${(report.urls || []).length} / ${(report.domains || []).length}`);
  addMetric("Findings", String((report.security_findings || []).length));

  artifactsEl.className = "artifacts";
  artifactsEl.innerHTML = "";
  Object.entries(data.artifacts || {}).forEach(([name, href]) => {
    const link = document.createElement("a");
    link.href = href;
    link.textContent = name;
    artifactsEl.appendChild(link);
  });
  if (!artifactsEl.children.length) {
    artifactsEl.textContent = "No downloadable artifacts yet.";
    artifactsEl.className = "artifacts empty";
  }
  modifyButton.disabled = data.status !== "analyzed";
}

function addMetric(label, value) {
  const item = document.createElement("div");
  item.className = "metric";
  item.innerHTML = `<b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span>`;
  summaryEl.appendChild(item);
}

function componentCount(components) {
  return String(Object.values(components).reduce((total, items) => total + (items || []).length, 0));
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

