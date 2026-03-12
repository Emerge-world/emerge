const SAMPLE_BASE_PATH = "fixtures";

function joinPath(basePath, fileName) {
  const trimmedBase = (basePath || "").replace(/\/+$/, "");
  return trimmedBase ? `${trimmedBase}/${fileName}` : fileName;
}

function getArtifactFileName(basePath, sampleFileName, runFileName) {
  return basePath === SAMPLE_BASE_PATH ? sampleFileName : runFileName;
}

async function fetchText(path) {
  const response = await fetch(path);
  if (!response.ok) {
    const error = new Error(`Failed to load ${path}`);
    error.status = response.status;
    throw error;
  }
  return response.text();
}

async function loadSummary(basePath) {
  const fileName = getArtifactFileName(basePath, "sample_summary.json", "summary.json");
  const text = await fetchText(joinPath(basePath, fileName));
  return JSON.parse(text);
}

async function loadTimeseries(basePath) {
  const fileName = getArtifactFileName(
    basePath,
    "sample_timeseries.jsonl",
    "timeseries.jsonl",
  );
  const text = await fetchText(joinPath(basePath, fileName));
  return text
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

async function loadEbs(basePath) {
  const fileName = getArtifactFileName(basePath, "sample_ebs.json", "ebs.json");
  const text = await fetchText(joinPath(basePath, fileName));
  return JSON.parse(text);
}

function normalizeResult(result) {
  if (result.status === "fulfilled") {
    return { status: "loaded", data: result.value };
  }
  if (result.reason && result.reason.status === 404) {
    return { status: "missing", data: null };
  }
  return { status: "invalid", data: null };
}

function renderArtifactStatus(artifacts) {
  const statusNode = document.getElementById("artifact-status");
  if (!statusNode) {
    return;
  }

  const labels = {
    loaded: "loaded",
    missing: "unavailable",
    invalid: "invalid",
  };

  statusNode.textContent =
    `summary: ${labels[artifacts.summary.status]} | ` +
    `timeseries: ${labels[artifacts.timeseries.status]} | ` +
    `ebs: ${labels[artifacts.ebs.status]}`;
}

function renderArtifactDetails(artifacts) {
  const detailsNode = document.getElementById("artifact-field-details");
  if (!detailsNode) {
    return;
  }

  detailsNode.textContent = JSON.stringify(
    {
      summary: artifacts.summary.status,
      timeseries: artifacts.timeseries.status,
      ebs: artifacts.ebs.status,
    },
    null,
    2,
  );
}

function renderArtifactPlaceholders(artifacts) {
  const summaryNode = document.getElementById("summary-cards");
  const timeseriesNode = document.getElementById("timeseries-panel");
  const ebsNode = document.getElementById("ebs-panels");

  if (summaryNode) {
    summaryNode.textContent =
      artifacts.summary.status === "loaded"
        ? "Summary artifacts loaded."
        : "Summary artifacts unavailable.";
  }

  if (timeseriesNode) {
    timeseriesNode.textContent =
      artifacts.timeseries.status === "loaded"
        ? "Timeseries artifacts loaded."
        : "Timeseries artifacts unavailable.";
  }

  if (ebsNode) {
    ebsNode.textContent =
      artifacts.ebs.status === "loaded"
        ? "EBS artifacts loaded."
        : "EBS artifacts unavailable.";
  }
}

async function loadArtifacts(basePath, mode) {
  const resolvedBasePath = mode === "sample" ? SAMPLE_BASE_PATH : basePath;
  const [summaryResult, timeseriesResult, ebsResult] = await Promise.allSettled([
    loadSummary(resolvedBasePath),
    loadTimeseries(resolvedBasePath),
    loadEbs(resolvedBasePath),
  ]);

  return {
    summary: normalizeResult(summaryResult),
    timeseries: normalizeResult(timeseriesResult),
    ebs: normalizeResult(ebsResult),
  };
}

async function handleArtifactLoad(basePath, mode) {
  const artifacts = await loadArtifacts(basePath, mode);
  renderArtifactStatus(artifacts);
  renderArtifactPlaceholders(artifacts);
  renderArtifactDetails(artifacts);
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("artifact-source-form");
  const pathInput = document.getElementById("artifact-path");
  const queryPath = new URLSearchParams(window.location.search).get("run");

  if (queryPath && pathInput) {
    pathInput.value = queryPath;
  }

  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(form);
      const mode = formData.get("artifact-mode") || "sample";
      const basePath = formData.get("artifact-path") || "";
      await handleArtifactLoad(String(basePath), String(mode));
    });
  }

  const initialMode = queryPath ? "path" : "sample";
  const initialBasePath = queryPath || "";
  handleArtifactLoad(initialBasePath, initialMode);
});
