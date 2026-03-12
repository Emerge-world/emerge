const SAMPLE_BASE_PATH = "fixtures";
const VIEW_MEANING = "meaning";
const VIEW_RUN = "run";

const pageState = {
  currentView: VIEW_MEANING,
  sourceOpen: false,
  artifacts: null,
};

const summaryDefinitions = [
  {
    label: "Survival",
    question: "Did the population endure through the end of the run?",
    formula: "Survival rate = final survivors / initial population",
    detail:
      "Built from the final survivor list, total deaths, and the starting population size.",
  },
  {
    label: "Action Quality",
    question: "How often did agent actions turn into valid world outcomes?",
    formula:
      "Oracle success rate = successful oracle resolutions / total oracle resolutions",
    detail:
      "Pairs with parse fail rate to show where decision parsing or resolution broke down.",
  },
  {
    label: "Innovation",
    question: "Did invention attempts become approved and reused behavior?",
    formula:
      "Innovation approval rate = approved innovations / innovation attempts",
    detail:
      "Realization tracks whether approved innovations were later executed in the run.",
  },
];

const chartDefinitions = [
  {
    key: "alive",
    label: "Alive agents",
    detail: "Shows whether the population is holding, shrinking, or stabilizing.",
    color: "var(--accent)",
  },
  {
    key: "mean_hunger",
    label: "Mean hunger",
    detail: "Higher values suggest mounting survival pressure and resource stress.",
    color: "var(--warm-accent)",
  },
  {
    key: "mean_energy",
    label: "Mean energy",
    detail: "Tracks whether agents can keep acting or are drifting into exhaustion.",
    color: "var(--realization)",
  },
  {
    key: "innovations_attempted",
    label: "Innovation attempts",
    detail: "Highlights when the population is experimenting with new behavior.",
    color: "var(--novelty)",
  },
];

const ebsDefinitions = {
  novelty: {
    label: "Novelty",
    description:
      "Measures whether approved innovations are varied and structurally different.",
    formula:
      "Novelty = 100 * (0.40 * approval_rate + 0.30 * category_diversity + 0.30 * structural_originality)",
    notes: [
      "approval_rate = approved innovations / innovation attempts",
      "category_diversity = distinct categories / 4",
      "structural_originality = approved innovations not classified as base_extension / approved innovations",
    ],
    color: "var(--novelty)",
  },
  utility: {
    label: "Utility",
    description:
      "Measures whether approved innovations appear to create useful state changes.",
    formula:
      "Utility = 100 * (0.50 * direct_state_improvement + 0.30 * future_option_value + 0.20 * execution_success_rate)",
    notes: [
      "direct_state_improvement = used approved innovations with positive welfare delta / used approved innovations",
      "welfare = life + energy - hunger",
      "The welfare change is measured over a 5-tick window before and after first use.",
      "future_option_value = approved innovations that produce non-stat items / approved innovations",
      "execution_success_rate = successful custom actions / total custom_action_executed events",
    ],
    color: "var(--utility)",
  },
  realization: {
    label: "Realization",
    description:
      "Measures whether approved innovations are actually used and succeed.",
    formula:
      "Realization = 100 * (0.60 * use_rate + 0.40 * execution_success_rate)",
    notes: [
      "use_rate = used approved innovations / approved innovations",
      "execution_success_rate = successful custom actions / total custom_action_executed events",
    ],
    color: "var(--realization)",
  },
  stability: {
    label: "Stability",
    description:
      "Measures how coherent behavior remains across invalid actions and contradictions.",
    formula:
      "Stability = clamp(100 - 40 * false_knowledge_rate - 30 * invalid_action_rate, 0, 100)",
    notes: [
      "false_knowledge_rate = contradictory learnings / total learnings",
      "invalid_action_rate = parse fails / total agent_decision events",
      "contradiction_rate is reported separately, but equals false_knowledge_rate in v1",
    ],
    color: "var(--stability)",
  },
  autonomy: {
    label: "Autonomy",
    description:
      "Measures proactive and environment-contingent behavior in the current implementation.",
    formula:
      "Autonomy = 100 * (0.40 * proactive_resource_acquisition + 0.30 * environment_contingent_innovation)",
    notes: [
      "proactive_resource_acquisition = non-hungry moves toward seen resources / total moves",
      "environment_contingent_innovation = innovation attempts with hunger > 60 / total innovation attempts",
      "self_generated_subgoals is reported as 0.0 and is not included in the current autonomy formula",
    ],
    color: "var(--autonomy)",
  },
};

function joinPath(basePath, fileName) {
  const trimmedBase = (basePath || "").replace(/\/+$/, "");
  return trimmedBase ? `${trimmedBase}/${fileName}` : fileName;
}

function getArtifactFileName(basePath, sampleFileName, runFileName) {
  return basePath === SAMPLE_BASE_PATH ? sampleFileName : runFileName;
}

function getByPath(target, path) {
  return path.split(".").reduce((current, part) => {
    if (current && Object.prototype.hasOwnProperty.call(current, part)) {
      return current[part];
    }
    return null;
  }, target);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function formatNumber(value) {
  if (typeof value !== "number") {
    return String(value);
  }
  if (Number.isInteger(value)) {
    return value.toString();
  }
  return value.toFixed(2);
}

function formatArtifactStatus(status) {
  if (status === "loaded") {
    return "loaded";
  }
  if (status === "missing") {
    return "unavailable";
  }
  return "invalid";
}

function buildStatusPill(label) {
  return `<span class="status-pill">${escapeHtml(label)}</span>`;
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

function renderMetricViewToggle() {
  const buttons = document.querySelectorAll("[data-view]");
  buttons.forEach((button) => {
    const isActive = button.dataset.view === pageState.currentView;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
}

function renderArtifactStatus(artifacts) {
  const statusNode = document.getElementById("artifact-status");
  if (!statusNode) {
    return;
  }

  const sourceLabel =
    artifacts.mode === "sample"
      ? "sample fixtures"
      : artifacts.basePath || "custom path";

  statusNode.textContent =
    `Source: ${sourceLabel} | ` +
    `summary: ${formatArtifactStatus(artifacts.summary.status)} | ` +
    `timeseries: ${formatArtifactStatus(artifacts.timeseries.status)} | ` +
    `ebs: ${formatArtifactStatus(artifacts.ebs.status)}`;
}

function renderSummaryCards() {
  const node = document.getElementById("summary-cards");
  if (!node) {
    return;
  }

  const artifacts = pageState.artifacts;

  if (pageState.currentView === VIEW_MEANING || !artifacts) {
    node.innerHTML = summaryDefinitions
      .map(
        (item) => `
          <article class="metric-card fade-in">
            <p class="metric-card__label">${escapeHtml(item.label)}</p>
            <h3>${escapeHtml(item.question)}</h3>
            <p class="metric-card__detail">${escapeHtml(item.detail)}</p>
            <p class="metric-card__formula">${escapeHtml(item.formula)}</p>
          </article>
        `,
      )
      .join("");
    return;
  }

  if (artifacts.summary.status !== "loaded") {
    node.innerHTML = `
      <article class="metric-card fade-in">
        ${buildStatusPill("Summary artifacts unavailable")}
        <p class="metric-card__detail">
          This section needs <code>summary.json</code> to render run-specific values.
        </p>
      </article>
    `;
    return;
  }

  const summary = artifacts.summary.data;
  const survivors = Array.isArray(summary.agents.final_survivors)
    ? summary.agents.final_survivors.length
    : 0;

  const cards = [
    {
      label: "Survival rate",
      value: formatPercent(summary.agents.survival_rate),
      detail: `${survivors} survivors from ${summary.agents.initial_count} starting agents. Deaths: ${summary.agents.deaths}.`,
    },
    {
      label: "Oracle success",
      value: formatPercent(summary.actions.oracle_success_rate),
      detail: `${summary.actions.total} decisions in the run. Parse fail rate: ${formatPercent(summary.actions.parse_fail_rate)}.`,
    },
    {
      label: "Innovation approval",
      value: formatPercent(summary.innovations.approval_rate),
      detail: `${summary.innovations.approved} approved out of ${summary.innovations.attempts} attempts. Realization: ${formatPercent(summary.innovations.realization_rate)}.`,
    },
  ];

  node.innerHTML = cards
    .map(
      (card) => `
        <article class="metric-card fade-in">
          <p class="metric-card__label">${escapeHtml(card.label)}</p>
          <div class="metric-card__value">${escapeHtml(card.value)}</div>
          <p class="metric-card__detail">${escapeHtml(card.detail)}</p>
        </article>
      `,
    )
    .join("");
}

function createSparkline(values, color) {
  if (!values.length) {
    return "";
  }

  const width = 240;
  const height = 96;
  const padding = 8;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = values.length === 1 ? 0 : (width - padding * 2) / (values.length - 1);
  const points = values
    .map((value, index) => {
      const x = padding + index * step;
      const y = height - padding - ((value - min) / range) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(" ");

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-hidden="true">
      <polyline
        fill="none"
        stroke="${color}"
        stroke-width="4"
        stroke-linecap="round"
        stroke-linejoin="round"
        points="${points}"
      />
    </svg>
  `;
}

function renderTimeseriesCharts() {
  const node = document.getElementById("timeseries-panel");
  if (!node) {
    return;
  }

  const artifacts = pageState.artifacts;

  if (pageState.currentView === VIEW_MEANING || !artifacts) {
    node.innerHTML = chartDefinitions
      .map(
        (item) => `
          <article class="chart-card fade-in">
            <p class="chart-card__label">${escapeHtml(item.label)}</p>
            <h3>${escapeHtml(item.label)}</h3>
            <p class="chart-card__detail">${escapeHtml(item.detail)}</p>
            ${buildStatusPill("Per-tick trend")}
          </article>
        `,
      )
      .join("");
    return;
  }

  if (artifacts.timeseries.status !== "loaded") {
    node.innerHTML = `
      <article class="chart-card fade-in">
        ${buildStatusPill("Timeseries artifacts unavailable")}
        <p class="chart-card__detail">
          This section needs <code>timeseries.jsonl</code> to render trend views.
        </p>
      </article>
    `;
    return;
  }

  const rows = artifacts.timeseries.data;
  node.innerHTML = chartDefinitions
    .map((item) => {
      const values = rows.map((row) => Number(row[item.key] || 0));
      const first = values[0];
      const last = values[values.length - 1];
      return `
        <article class="chart-card fade-in">
          <p class="chart-card__label">${escapeHtml(item.label)}</p>
          <h3>${escapeHtml(formatNumber(last))}</h3>
          <p class="chart-card__detail">${escapeHtml(item.detail)}</p>
          ${createSparkline(values, item.color)}
          <p class="chart-card__range">
            Starts at ${escapeHtml(formatNumber(first))} and ends at ${escapeHtml(formatNumber(last))}.
          </p>
        </article>
      `;
    })
    .join("");
}

function renderEbsPanels() {
  const node = document.getElementById("ebs-panels");
  if (!node) {
    return;
  }

  const artifacts = pageState.artifacts;

  if (pageState.currentView === VIEW_MEANING || !artifacts) {
    node.innerHTML = Object.entries(ebsDefinitions)
      .map(
        ([key, definition]) => `
          <article class="ebs-panel fade-in">
            <p class="ebs-panel__label">${escapeHtml(definition.label)}</p>
            <h3>${escapeHtml(definition.label)}</h3>
            <p class="ebs-panel__detail">${escapeHtml(definition.description)}</p>
            <p class="metric-card__formula">${escapeHtml(definition.formula)}</p>
            <ul class="ebs-panel__list">
              ${definition.notes
                .map((note) => `<li>${escapeHtml(note)}</li>`)
                .join("")}
            </ul>
            <div class="ebs-panel__bar">
              <div class="ebs-panel__fill" style="width: 100%; background: ${definition.color};"></div>
            </div>
            <div class="ebs-panel__meta">
              <span>Weight</span>
              <strong>${escapeHtml(
                formatNumber(getByPath(
                  {
                    novelty: 0.3,
                    utility: 0.2,
                    realization: 0.2,
                    stability: 0.15,
                    autonomy: 0.15,
                  },
                  key,
                )),
              )}</strong>
            </div>
          </article>
        `,
      )
      .join("");
    return;
  }

  if (artifacts.ebs.status !== "loaded") {
    node.innerHTML = `
      <article class="ebs-panel fade-in">
        ${buildStatusPill("EBS artifacts unavailable")}
        <p class="ebs-panel__detail">
          This section needs <code>ebs.json</code> to render component scores.
        </p>
      </article>
    `;
    return;
  }

  const components = artifacts.ebs.data.components;
  node.innerHTML = Object.entries(ebsDefinitions)
    .map(([key, definition]) => {
      const component = components[key];
      const subScores = Object.entries(component.sub_scores)
        .map(
          ([subKey, value]) =>
            `<li>${escapeHtml(subKey)}: ${escapeHtml(formatNumber(value))}</li>`,
        )
        .join("");
      return `
        <article class="ebs-panel fade-in">
          <p class="ebs-panel__label">${escapeHtml(definition.label)}</p>
          <div class="ebs-panel__score">${escapeHtml(formatNumber(component.score))}</div>
          <p class="ebs-panel__detail">${escapeHtml(definition.description)}</p>
          <div class="ebs-panel__bar">
            <div
              class="ebs-panel__fill"
              style="width: ${Math.max(0, Math.min(100, component.score))}%; background: ${definition.color};"
            ></div>
          </div>
          <div class="ebs-panel__meta">
            <span>Weight</span>
            <strong>${escapeHtml(formatNumber(component.weight))}</strong>
          </div>
          <ul class="ebs-panel__list">${subScores}</ul>
        </article>
      `;
    })
    .join("");
}

function renderArtifactDetails() {
  const detailsNode = document.getElementById("artifact-field-details");
  const toggle = document.getElementById("artifact-source-toggle");

  if (!detailsNode || !toggle || !pageState.artifacts) {
    return;
  }

  detailsNode.classList.toggle("is-hidden", !pageState.sourceOpen);
  toggle.setAttribute("aria-expanded", String(pageState.sourceOpen));
  toggle.textContent = pageState.sourceOpen ? "Hide data source" : "Show data source";

  const artifacts = pageState.artifacts;
  const sections = [
    {
      file: artifacts.mode === "sample" ? "sample_summary.json" : "summary.json",
      label: "Summary artifact",
      status: artifacts.summary.status,
      fields: "agents.*, actions.*, innovations.*",
    },
    {
      file:
        artifacts.mode === "sample"
          ? "sample_timeseries.jsonl"
          : "timeseries.jsonl",
      label: "Timeseries artifact",
      status: artifacts.timeseries.status,
      fields:
        "tick, sim_time, alive, mean_life, mean_hunger, mean_energy, deaths, actions, oracle_success_rate, innovations_attempted, innovations_approved",
    },
    {
      file: artifacts.mode === "sample" ? "sample_ebs.json" : "ebs.json",
      label: "EBS artifact",
      status: artifacts.ebs.status,
      fields: "ebs, components.*, innovations[]",
    },
  ];

  detailsNode.innerHTML = `
    <div class="fade-in">
      <p class="section-kicker">Source Detail</p>
      <h3>Where the numbers come from</h3>
      <p class="section-intro">
        The page loads each artifact independently and marks missing files as unavailable instead of failing the whole explainer.
      </p>
      <div class="metric-grid">
        ${sections
          .map(
            (section) => `
              <article class="metric-card">
                <p class="metric-card__label">${escapeHtml(section.label)}</p>
                <h3>${escapeHtml(section.file)}</h3>
                <p class="metric-card__detail">Status: ${escapeHtml(
                  formatArtifactStatus(section.status),
                )}</p>
                <p class="metric-card__detail">${escapeHtml(section.fields)}</p>
              </article>
            `,
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderDashboard() {
  renderMetricViewToggle();
  renderArtifactStatus(pageState.artifacts);
  renderSummaryCards();
  renderTimeseriesCharts();
  renderEbsPanels();
  renderArtifactDetails();
}

async function loadArtifacts(basePath, mode) {
  const resolvedBasePath = mode === "sample" ? SAMPLE_BASE_PATH : basePath;
  const [summaryResult, timeseriesResult, ebsResult] = await Promise.allSettled([
    loadSummary(resolvedBasePath),
    loadTimeseries(resolvedBasePath),
    loadEbs(resolvedBasePath),
  ]);

  return {
    mode,
    basePath: resolvedBasePath,
    summary: normalizeResult(summaryResult),
    timeseries: normalizeResult(timeseriesResult),
    ebs: normalizeResult(ebsResult),
  };
}

async function handleArtifactLoad(basePath, mode) {
  pageState.artifacts = await loadArtifacts(basePath, mode);
  renderDashboard();
}

function syncArtifactModeControls(selectedMode) {
  const pathInput = document.getElementById("artifact-path");
  if (!pathInput) {
    return;
  }
  pathInput.disabled = selectedMode !== "path";
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("artifact-source-form");
  const pathInput = document.getElementById("artifact-path");
  const sourceToggle = document.getElementById("artifact-source-toggle");
  const queryPath = new URLSearchParams(window.location.search).get("run");

  if (queryPath && pathInput) {
    pathInput.value = queryPath;
  }

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      pageState.currentView = button.dataset.view || VIEW_MEANING;
      renderDashboard();
    });
  });

  if (sourceToggle) {
    sourceToggle.addEventListener("click", () => {
      pageState.sourceOpen = !pageState.sourceOpen;
      renderArtifactDetails();
    });
  }

  if (form) {
    const modeInputs = form.querySelectorAll('input[name="artifact-mode"]');
    modeInputs.forEach((input) => {
      input.addEventListener("change", () => {
        syncArtifactModeControls(input.value);
      });
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(form);
      const mode = String(formData.get("artifact-mode") || "sample");
      const basePath = String(formData.get("artifact-path") || "");
      await handleArtifactLoad(basePath, mode);
    });
  }

  const initialMode = queryPath ? "path" : "sample";
  if (queryPath && form) {
    const pathRadio = form.querySelector('input[value="path"]');
    if (pathRadio) {
      pathRadio.checked = true;
    }
  }
  syncArtifactModeControls(initialMode);
  handleArtifactLoad(queryPath || "", initialMode);
});
