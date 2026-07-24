const REPOSITORY_DATA_BASE =
  "https://raw.githubusercontent.com/akiokuyama/J1League_score_prediction_site/main/outputs";
const PAST_RESULTS_BASE = "./data/past_prediction_results";
const STANDINGS_FORECAST_BASE = `${REPOSITORY_DATA_BASE}/standings_forecast`;

const DATA_URLS = {
  upcoming: `${REPOSITORY_DATA_BASE}/all_unplayed_predictions.json`,
  latest: `${REPOSITORY_DATA_BASE}/latest_predictions.json`,
  pastIndex: `${PAST_RESULTS_BASE}/index.json`,
  standings: `${STANDINGS_FORECAST_BASE}/latest.json`,
  standingsIndex: `${STANDINGS_FORECAST_BASE}/index.json`,
};

const TEAM_STORAGE_KEY = "j1_prediction_my_team_v1";
const THEME_STORAGE_KEY = "j1_prediction_theme_v1";

function trackAnalytics(eventName, parameters = {}) {
  window.J1Analytics?.track(eventName, {
    app_surface: "pwa",
    ...parameters,
  });
}

function trackAnalyticsOnce(eventName, parameters = {}, eventKey = eventName) {
  window.J1Analytics?.trackOnce(
    eventName,
    {
      app_surface: "pwa",
      ...parameters,
    },
    `pwa:${eventKey}`,
  );
}

function currentDisplayMode() {
  if (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  ) {
    return "standalone";
  }
  return "browser";
}

function trackAppOpen() {
  trackAnalyticsOnce(
    "app_open",
    {
      display_mode: currentDisplayMode(),
      has_my_team: Boolean(state.myTeam),
    },
    "app_open",
  );
}

const TEAM_NAMES = {
  kasm: "鹿島アントラーズ",
  mito: "水戸ホーリーホック",
  uraw: "浦和レッズ",
  chib: "ジェフユナイテッド千葉",
  kasw: "柏レイソル",
  FCtk: "FC東京",
  fctk: "FC東京",
  "tk-v": "東京ヴェルディ",
  mcd: "FC町田ゼルビア",
  "ka-f": "川崎フロンターレ",
  "y-fm": "横浜Ｆ・マリノス",
  shim: "清水エスパルス",
  nago: "名古屋グランパス",
  kyot: "京都サンガF.C.",
  "g-os": "ガンバ大阪",
  "c-os": "セレッソ大阪",
  kobe: "ヴィッセル神戸",
  okay: "ファジアーノ岡山",
  hiro: "サンフレッチェ広島",
  fuku: "アビスパ福岡",
  ngsk: "Ｖ・ファーレン長崎",
};

const TEAM_NAME_TO_CODE = Object.fromEntries(
  Object.entries(TEAM_NAMES).map(([code, name]) => [name, code]),
);

const TEAM_EMBLEM_CELLS = {
  kasm: [7, 0],
  mito: [8, 0],
  uraw: [2, 1],
  chib: [4, 1],
  kasw: [5, 1],
  FCtk: [6, 1],
  fctk: [6, 1],
  "tk-v": [7, 1],
  mcd: [8, 1],
  "ka-f": [9, 1],
  "y-fm": [0, 2],
  shim: [0, 3],
  nago: [3, 3],
  kyot: [6, 3],
  "g-os": [7, 3],
  "c-os": [8, 3],
  kobe: [0, 4],
  okay: [3, 4],
  hiro: [4, 4],
  fuku: [1, 5],
  ngsk: [4, 5],
};

const initialMyTeam = readStoredTeam();
const initialTheme = readStoredTheme();
const installIntent = new URLSearchParams(window.location.search).get("install") === "1";

const state = {
  view: "upcoming",
  data: {
    upcoming: null,
    latest: null,
    pastIndex: null,
    pastSeasons: {},
    standings: null,
    standingsIndex: null,
    standingsForecasts: [],
  },
  myTeam: initialMyTeam,
  teamFilter: initialMyTeam ? "my-team" : "all",
  pastSeason: "2026_27_j1",
  standingsSnapshot: null,
  theme: initialTheme,
  installPrompt: null,
  installCompleted: false,
  installIntent,
};

const content = document.querySelector("#app-content");
const statusCard = document.querySelector("#status-card");
const statusTitle = document.querySelector("#status-title");
const statusDetail = document.querySelector("#status-detail");
const connectionBanner = document.querySelector("#connection-banner");
const myTeamBanner = document.querySelector("#my-team-banner");
const myTeamIdentity = document.querySelector("#my-team-identity");
const teamDialog = document.querySelector("#team-dialog");
const teamOptions = document.querySelector("#team-options");
const matchDialog = document.querySelector("#match-dialog");
const matchDetail = document.querySelector("#match-detail");
const installDialog = document.querySelector("#install-dialog");
const installInstructions = document.querySelector("#install-instructions");
const installDialogAction = document.querySelector("#install-dialog-action");
const installButton = document.querySelector("#install-button");
const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");

applyTheme(state.theme, { persist: false });
const handleSystemThemeChange = () => {
  if (state.theme === "system") updateThemeColor();
};
if (typeof systemTheme.addEventListener === "function") {
  systemTheme.addEventListener("change", handleSystemThemeChange);
} else {
  systemTheme.addListener?.(handleSystemThemeChange);
}

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => {
    state.view = button.dataset.view;
    trackAnalytics("view_app_section", { section_name: state.view });
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.classList.toggle("is-active", item === button);
    });
    render();
    content.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
});

document.querySelector("#change-team-button").addEventListener("click", openTeamDialog);

installButton.addEventListener("click", requestAppInstall);
installDialogAction.addEventListener("click", async () => {
  closeDialog(installDialog);
  await requestAppInstall();
});

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  state.installPrompt = event;
  trackAnalyticsOnce("install_prompt_available", {}, "install_prompt_available");
  installButton.hidden = false;
  if (state.view === "settings") renderSettings();
  if (state.installIntent && installDialog.open) showInstallInstructions();
});

window.addEventListener("appinstalled", () => {
  state.installPrompt = null;
  state.installCompleted = true;
  trackAnalytics("app_installed", { display_mode: "standalone" });
  installButton.hidden = true;
  if (state.view === "settings") renderSettings();
});

window.addEventListener("online", updateConnectionState);
window.addEventListener("offline", updateConnectionState);
window.addEventListener("j1analyticsconsentchange", trackAppOpen);

initialize();

async function initialize() {
  updateConnectionState();
  registerServiceWorker();
  trackAppOpen();

  try {
    const dataEntries = Object.entries(DATA_URLS);
    const results = await Promise.allSettled(
      dataEntries.map(async ([key, url]) => {
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`${key}: HTTP ${response.status}`);
        }
        return [key, await response.json()];
      }),
    );

    const failures = [];
    for (const [index, result] of results.entries()) {
      const key = dataEntries[index][0];
      if (result.status === "fulfilled") {
        const [resultKey, value] = result.value;
        state.data[resultKey] = value;
      } else if (key !== "standingsIndex") {
        failures.push(result.reason);
      }
    }

    if (state.data.pastIndex) {
      const pastSeasonResults = await loadPastSeasonData(state.data.pastIndex);
      state.data.pastSeasons = pastSeasonResults.data;
      failures.push(...pastSeasonResults.failures);
      const configuredDefault = state.data.pastIndex.default_season;
      if (configuredDefault && state.data.pastSeasons[configuredDefault]) {
        state.pastSeason = configuredDefault;
      }
    }

    const standingsResults = await loadStandingsForecasts(state.data.standingsIndex, state.data.standings);
    state.data.standingsForecasts = standingsResults.data;
    failures.push(...standingsResults.failures);
    if (state.data.standingsForecasts.length) {
      state.standingsSnapshot =
        state.data.standingsIndex?.default_forecast || state.data.standingsForecasts[0].generated_at;
    }

    if (!state.data.upcoming && state.data.latest) {
      state.data.upcoming = state.data.latest;
    }
    if (
      !state.data.upcoming &&
      !Object.keys(state.data.pastSeasons).length &&
      !state.data.standingsForecasts.length
    ) {
      throw new Error("表示できる予測データを取得できませんでした。");
    }

    const availableTeams = getAvailableTeams();
    if (state.myTeam && !availableTeams.includes(state.myTeam)) {
      state.myTeam = null;
      state.teamFilter = "all";
      localStorage.removeItem(TEAM_STORAGE_KEY);
    }

    setReadyStatus(failures.length > 0);
    renderMyTeamBanner();
    render();
    trackAnalyticsOnce("view_app_section", { section_name: state.view }, `initial_view:${state.view}`);

    if (state.installIntent) {
      state.view = "settings";
      selectNavigation("settings");
      render();
      window.history.replaceState({}, "", window.location.pathname);
      window.setTimeout(showInstallInstructions, 300);
    } else if (!state.myTeam) {
      openTeamDialog();
    }
  } catch (error) {
    setErrorStatus(error);
    renderError(error);
  }
}

async function loadPastSeasonData(index) {
  const seasons = Array.isArray(index?.seasons) ? index.seasons : [];
  const results = await Promise.allSettled(
    seasons.map(async (season) => {
      if (!season?.key || !season?.data_file) {
        throw new Error("過去結果のシーズン設定が不正です。");
      }
      const response = await fetch(`${PAST_RESULTS_BASE}/${season.data_file}`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`past:${season.key}: HTTP ${response.status}`);
      }
      return [season.key, await response.json()];
    }),
  );
  const data = {};
  const failures = [];
  for (const result of results) {
    if (result.status === "fulfilled") {
      const [key, value] = result.value;
      data[key] = value;
    } else {
      failures.push(result.reason);
    }
  }
  return { data, failures };
}

async function loadStandingsForecasts(index, latest) {
  const entries = Array.isArray(index?.forecasts) ? index.forecasts : [];
  const results = await Promise.allSettled(
    entries.map(async (entry) => {
      if (!entry?.data_file) {
        throw new Error("順位予測の履歴設定が不正です。");
      }
      const response = await fetch(`${STANDINGS_FORECAST_BASE}/${entry.data_file}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`standings:${entry.generated_at || entry.data_file}: HTTP ${response.status}`);
      }
      return await response.json();
    }),
  );
  const data = latest ? [latest] : [];
  const failures = [];
  for (const result of results) {
    if (result.status === "fulfilled") {
      data.push(result.value);
    } else {
      failures.push(result.reason);
    }
  }
  const seen = new Set();
  const unique = data
    .filter((forecast) => {
      const identity = String(forecast?.generated_at || "");
      if (!identity || seen.has(identity)) return false;
      seen.add(identity);
      return Array.isArray(forecast?.teams) && forecast.teams.length > 0;
    })
    .sort((a, b) => String(b.generated_at).localeCompare(String(a.generated_at)));
  return { data: unique, failures };
}

function setReadyStatus(partial) {
  const updated = getLatestUpdate();
  statusCard.classList.remove("is-error");
  statusCard.classList.add("is-ready");
  statusTitle.textContent = partial ? "一部のデータを表示しています" : "最新の予測データ";
  statusDetail.textContent = updated ? `更新 ${formatDateTime(updated)}` : "更新日時を確認できません";
}

function setErrorStatus(error) {
  statusCard.classList.remove("is-ready");
  statusCard.classList.add("is-error");
  statusTitle.textContent = "予測データを取得できません";
  statusDetail.textContent = error instanceof Error ? error.message : String(error);
  trackAnalytics("data_load_error", { error_area: "initial_data" });
}

function updateConnectionState() {
  const offline = !navigator.onLine;
  connectionBanner.hidden = !offline;
}

function getLatestUpdate() {
  const values = [
    state.data.upcoming?.last_updated,
    state.data.latest?.last_updated,
    state.data.pastSeasons[state.pastSeason]?.generated_at,
    state.data.standingsForecasts[0]?.generated_at,
  ].filter(Boolean);
  if (!values.length) return null;
  return values
    .map((value) => new Date(value))
    .filter((value) => !Number.isNaN(value.getTime()))
    .sort((a, b) => b - a)[0];
}

function render() {
  if (
    !state.data.upcoming &&
    !Object.keys(state.data.pastSeasons).length &&
    !state.data.standingsForecasts.length
  ) {
    return;
  }

  if (state.view === "upcoming") {
    renderUpcoming();
  } else if (state.view === "past") {
    renderPast();
  } else if (state.view === "standings") {
    renderStandings();
  } else {
    renderSettings();
  }
}

function renderUpcoming() {
  const matches = safeMatches(state.data.upcoming);
  const filtered = filterMatches(matches, { limitAllWithoutMyTeam: true });
  const teamOptionsHtml = buildTeamFilterOptions();

  content.innerHTML = `
    <div class="view-heading">
      <div>
        <h2>これからの試合</h2>
        <p>${filtered.length} / ${matches.length}試合</p>
      </div>
      <select id="upcoming-team-filter" class="filter-control" aria-label="表示するチーム">
        ${teamOptionsHtml}
      </select>
    </div>
    <div class="match-list">
      ${filtered.length ? filtered.map(renderUpcomingCard).join("") : renderEmptyState()}
    </div>
  `;

  bindTeamFilter("#upcoming-team-filter");
  bindMatchCards(matches);
}

function renderPast() {
  const seasonMeta = getPastSeasonMetadata(state.pastSeason);
  const matches = safeMatches(state.data.pastSeasons[state.pastSeason]);
  const filtered = filterMatches(matches);

  content.innerHTML = `
    <div class="view-heading">
      <div>
        <h2>過去の予測結果</h2>
        <p>${filtered.length} / ${matches.length}試合</p>
      </div>
    </div>
    <div class="filter-stack">
      <label class="filter-field">
        <span>シーズン</span>
        <select id="past-season-filter" class="filter-control" aria-label="表示するシーズン">
          ${buildPastSeasonOptions()}
        </select>
      </label>
      ${
        matches.length
          ? `<label class="filter-field">
              <span>チーム</span>
              <select id="past-team-filter" class="filter-control" aria-label="表示するチーム">
                ${buildTeamFilterOptions()}
              </select>
            </label>`
          : ""
      }
    </div>
    ${renderPastCoverageNotice(seasonMeta)}
    <div class="match-list">
      ${
        filtered.length
          ? filtered.map(renderPastCard).join("")
          : matches.length
            ? renderEmptyState()
            : renderCurrentSeasonEmptyState()
      }
    </div>
  `;

  bindPastSeasonFilter();
  if (matches.length) bindTeamFilter("#past-team-filter");
  bindMatchCards(matches);
}

function renderStandings() {
  const forecasts = state.data.standingsForecasts;
  const forecast =
    forecasts.find((item) => item.generated_at === state.standingsSnapshot) || forecasts[0] || null;
  const teams = Array.isArray(forecast?.teams) ? forecast.teams : [];
  const completed = forecast?.data_as_of?.completed_matches ?? 0;
  const generated = forecast?.generated_at ? formatDateTime(forecast.generated_at) : "-";

  content.innerHTML = `
    <div class="view-heading">
      <div>
        <h2>シーズン最終順位予測</h2>
        <p>${escapeHtml(generated)}時点・終了済み${Number(completed)}試合</p>
      </div>
    </div>
    ${
      forecasts.length
        ? `<label class="filter-field standings-snapshot-filter">
            <span>予測した日時</span>
            <select id="standings-snapshot-filter" class="filter-control" aria-label="表示する順位予測の日時">
              ${forecasts
                .map(
                  (item) =>
                    `<option value="${escapeAttribute(item.generated_at)}" ${
                      item.generated_at === forecast?.generated_at ? "selected" : ""
                    }>${escapeHtml(formatForecastDateTime(item.generated_at))}</option>`,
                )
                .join("")}
            </select>
          </label>`
        : ""
    }
    <div class="standings-list">
      ${teams.length ? teams.map(renderStandingsCard).join("") : renderEmptyState()}
    </div>
  `;

  document.querySelector("#standings-snapshot-filter")?.addEventListener("change", (event) => {
    state.standingsSnapshot = event.target.value;
    trackAnalytics("select_standings_snapshot", {
      snapshot_date: String(event.target.value).slice(0, 10),
    });
    renderStandings();
  });
}

function renderSettings() {
  const isStandalone = isInstalledApp();
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const installText = isStandalone
    ? "このアプリはホーム画面から起動しています。"
    : state.installPrompt
      ? "ホーム画面に追加すると、次回からアプリのようにすぐ起動できます。"
      : ios
        ? "ボタンを押すと、iPhoneでホーム画面に追加する手順を確認できます。"
        : "ボタンを押すと、この端末で利用できる追加方法を確認できます。";
  const installButtonLabel = isStandalone ? "ホーム画面に追加済み" : "ホーム画面に追加";

  content.innerHTML = `
    <div class="view-heading">
      <div>
        <h2>設定</h2>
        <p>端末ごとの表示設定</p>
      </div>
    </div>
    <section class="panel">
      <div class="settings-section">
        <h3>マイチーム</h3>
        <p>${state.myTeam ? `${escapeHtml(displayTeam(state.myTeam))}を設定中です。` : "まだ設定されていません。"}</p>
        <button id="settings-team-button" class="primary-button full-width" type="button">マイチームを選択</button>
      </div>
      <div class="settings-section">
        <h3>表示テーマ</h3>
        <p>この端末で使用する画面の明るさを選択できます。</p>
        <div class="theme-options" role="radiogroup" aria-label="表示テーマ">
          ${renderThemeOption("system", "端末設定")}
          ${renderThemeOption("light", "ライト")}
          ${renderThemeOption("dark", "ダーク")}
        </div>
      </div>
      <div class="settings-section">
        <h3>ホーム画面に追加</h3>
        <p>${escapeHtml(installText)}</p>
        <button id="settings-install-button" class="${isStandalone ? "secondary-button" : "primary-button"} full-width" type="button" ${isStandalone ? "disabled" : ""}>
          ${installButtonLabel}
        </button>
      </div>
      <div class="settings-section">
        <h3>保存データ</h3>
        <p>マイチームと表示テーマの設定値は、この端末のブラウザ内に保存されます。</p>
        <button id="clear-team-button" class="secondary-button danger-button full-width" type="button" ${state.myTeam ? "" : "disabled"}>
          マイチーム設定を解除
        </button>
      </div>
      <div class="settings-section">
        <h3>利用状況データ</h3>
        <p>
          現在は<strong data-analytics-consent-status>未選択</strong>です。
          許可した場合のみ、サービス改善のため画面表示や操作をGoogle Analyticsへ送信します。
        </p>
        <div class="analytics-setting-actions" aria-label="利用状況データの送信設定">
          <button class="secondary-button" type="button" data-analytics-consent="granted">送信を許可</button>
          <button class="secondary-button" type="button" data-analytics-consent="denied">送信を停止</button>
        </div>
        <div class="privacy-note">
          氏名やメールアドレスなど、個人を直接特定する情報は送信しません。
          マイチームを変更した場合は、クラブ識別コードと操作種別のみを送信します。
        </div>
      </div>
      <div class="settings-section">
        <h3>この予測について</h3>
        <p>機械学習モデルによる参考予測です。実際の試合結果を保証するものではありません。</p>
      </div>
    </section>
  `;

  document.querySelector("#settings-team-button").addEventListener("click", openTeamDialog);
  document.querySelector("#settings-install-button")?.addEventListener("click", requestAppInstall);
  document.querySelector("#clear-team-button")?.addEventListener("click", clearMyTeam);
  document.querySelectorAll('input[name="theme"]').forEach((input) => {
    input.addEventListener("change", (event) => applyTheme(event.target.value));
  });
  window.J1Analytics?.bindConsentControls(content);
  window.J1Analytics?.updateConsentUi();
}

function renderThemeOption(value, label) {
  return `
    <label class="theme-option">
      <input type="radio" name="theme" value="${value}" ${state.theme === value ? "checked" : ""}>
      <span>${label}</span>
    </label>
  `;
}

function applyTheme(theme, { persist = true } = {}) {
  const selected = ["system", "light", "dark"].includes(theme) ? theme : "system";
  state.theme = selected;
  if (selected === "system") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.dataset.theme = selected;
  }
  if (persist) {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, selected);
    } catch {
      // 保存できない環境でも、現在の画面には選択を反映します。
    }
    trackAnalytics("theme_changed", { theme: selected });
  }
  updateThemeColor();
}

function updateThemeColor() {
  const dark = state.theme === "dark" || (state.theme === "system" && systemTheme.matches);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#0c1720" : "#f2f6f8");
}

function renderUpcomingCard(match) {
  const home = normalizeTeam(match.home_team);
  const away = normalizeTeam(match.away_team);
  const score = formatScore(match.predicted_score);
  const probabilities = match.result_probabilities || {};

  return `
    <button class="match-card" type="button" data-match-id="${escapeAttribute(match.match_id)}">
      <div class="match-meta">
        <span>${escapeHtml(formatDate(match.date))}</span>
        <span>第${escapeHtml(String(match.section ?? match.matchweek ?? "-"))}節</span>
      </div>
      ${renderMatchup(home, away, score, "予測")}
      ${renderProbabilityRow(probabilities)}
    </button>
  `;
}

function renderPastCard(match) {
  const home = normalizeTeam(match.home_team);
  const away = normalizeTeam(match.away_team);
  const predicted = formatScore(match.predicted_score);
  const actual = formatScore(match.actual_score);
  const resultCorrect = Boolean(match.is_result_correct);
  const scoreCorrect = Boolean(match.is_score_correct);

  return `
    <button class="match-card" type="button" data-match-id="${escapeAttribute(match.match_id)}">
      <div class="match-meta">
        <span>${escapeHtml(formatDate(match.date))}</span>
        <span>第${escapeHtml(String(match.matchweek ?? match.section ?? "-"))}節</span>
      </div>
      ${renderMatchup(home, away, actual, "結果")}
      <div class="result-badges">
        <span class="badge ${resultCorrect ? "is-correct" : "is-wrong"}">勝敗${resultCorrect ? "的中" : "外れ"}</span>
        <span class="badge ${scoreCorrect ? "is-correct" : "is-wrong"}">スコア${scoreCorrect ? "的中" : "外れ"}</span>
        <span class="badge">予測 ${escapeHtml(predicted)}</span>
      </div>
    </button>
  `;
}

function renderStandingsCard(team) {
  const code = normalizeTeam(team.team || team.team_name);
  const rank = Number(team.predicted_rank || 0);
  const classes = ["standings-card"];
  if (rank <= 3) classes.push("is-top-three");
  if (state.myTeam && code === state.myTeam) classes.push("is-my-team");
  const current = team.current_rank ? `現在 ${team.current_rank}位` : "現在 -";
  const change = formatRankChange(team.rank_change);
  const range =
    team.likely_rank_low && team.likely_rank_high
      ? `想定 ${team.likely_rank_low}〜${team.likely_rank_high}位`
      : "想定 -";

  return `
    <article class="${classes.join(" ")}">
      <div class="standings-main">
        <div class="rank-block"><span>予測順位</span><strong>${rank}</strong></div>
        <div class="team-identity">
          ${teamLogo(code)}
          <span class="team-identity-name">${escapeHtml(team.team_name || displayTeam(code))}</span>
        </div>
        <div class="points-block"><span>期待勝点</span><strong>${formatNumber(team.expected_points, 1)}</strong></div>
      </div>
      <div class="standings-context">
        <span class="context-chip">${escapeHtml(current)}</span>
        <span class="context-chip">${escapeHtml(change)}</span>
        <span class="context-chip">${escapeHtml(range)}</span>
      </div>
      ${renderProbabilityRow({
        home_win: team.champion_probability,
        draw: team.top3_probability,
        away_win: team.bottom3_probability,
      }, ["優勝", "Top 3", "下位3"])}
    </article>
  `;
}

function renderMatchup(home, away, score, label) {
  return `
    <div class="match-teams">
      <div class="match-team">
        ${teamLogo(home)}
        <span class="match-team-name">${escapeHtml(displayTeam(home))}</span>
      </div>
      <div class="score-block">
        <span class="score-value">${escapeHtml(score)}</span>
        <span class="score-label">${escapeHtml(label)}</span>
      </div>
      <div class="match-team">
        ${teamLogo(away)}
        <span class="match-team-name">${escapeHtml(displayTeam(away))}</span>
      </div>
    </div>
  `;
}

function renderProbabilityRow(probabilities, labels = ["ホーム", "引分", "アウェイ"]) {
  const values = [
    probabilities.home_win,
    probabilities.draw,
    probabilities.away_win,
  ];
  return `
    <div class="probability-row">
      ${labels
        .map(
          (label, index) => `
            <span class="probability-item">
              ${escapeHtml(label)}
              <strong>${formatPercent(values[index])}</strong>
            </span>
          `,
        )
        .join("")}
    </div>
  `;
}

function bindMatchCards(matches) {
  const byId = new Map(matches.map((match) => [String(match.match_id), match]));
  document.querySelectorAll("[data-match-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const match = byId.get(button.dataset.matchId);
      if (match) openMatchDialog(match);
    });
  });
}

function openMatchDialog(match) {
  const home = normalizeTeam(match.home_team);
  const away = normalizeTeam(match.away_team);
  const score = formatScore(match.actual_score || match.predicted_score);
  const label = match.actual_score ? "試合結果" : "予測スコア";
  const expected = match.expected_goals || {};
  const scoreCandidates = Array.isArray(match.score_candidates) ? match.score_candidates.slice(0, 5) : [];
  const scorers = match.scorer_candidates || {};
  trackAnalytics("view_match_detail", {
    match_id: String(match.match_id || "").slice(0, 100),
    match_status: match.actual_score ? "completed" : "upcoming",
    home_team_code: home,
    away_team_code: away,
  });

  matchDetail.innerHTML = `
    <div class="dialog-heading">
      <div>
        <p class="eyebrow">${escapeHtml(formatDate(match.date))}</p>
        <h2>試合詳細</h2>
      </div>
      <form method="dialog"><button class="icon-button" type="submit" aria-label="閉じる">×</button></form>
    </div>
    ${renderMatchup(home, away, score, label)}
    ${match.result_probabilities ? renderProbabilityRow(match.result_probabilities) : ""}
    ${
      expected.home != null || expected.away != null
        ? `<section class="detail-section"><h3>期待得点</h3><p>${escapeHtml(displayTeam(home))} ${formatNumber(expected.home, 2)} − ${formatNumber(expected.away, 2)} ${escapeHtml(displayTeam(away))}</p></section>`
        : ""
    }
    ${
      scoreCandidates.length
        ? `<section class="detail-section"><h3>スコア候補</h3><ol class="detail-list">${scoreCandidates
            .map((candidate) => `<li>${escapeHtml(candidate.score)}・${formatPercent(candidate.probability)}</li>`)
            .join("")}</ol></section>`
        : ""
    }
    ${renderScorerSection(scorers, home, away)}
  `;
  showDialog(matchDialog);
}

function renderScorerSection(scorers, home, away) {
  const homeScorers = Array.isArray(scorers.home) ? scorers.home.slice(0, 3) : [];
  const awayScorers = Array.isArray(scorers.away) ? scorers.away.slice(0, 3) : [];
  if (!homeScorers.length && !awayScorers.length) return "";

  return `
    <section class="detail-section">
      <h3>得点者候補 Top 3</h3>
      ${renderScorers(displayTeam(home), homeScorers)}
      ${renderScorers(displayTeam(away), awayScorers)}
    </section>
  `;
}

function renderScorers(teamName, players) {
  if (!players.length) return "";
  return `
    <h3>${escapeHtml(teamName)}</h3>
    <ol class="detail-list">
      ${players.map((player) => `<li>${escapeHtml(player.player || "-")}・${formatPercent(player.probability)}</li>`).join("")}
    </ol>
  `;
}

function filterMatches(matches, { limitAllWithoutMyTeam = false } = {}) {
  if (state.teamFilter === "all") {
    return limitAllWithoutMyTeam && !state.myTeam ? matches.slice(0, 40) : matches;
  }
  const selected = state.teamFilter === "my-team" ? state.myTeam : state.teamFilter;
  if (!selected) {
    return matches.slice(0, 40);
  }
  return matches.filter(
    (match) =>
      normalizeTeam(match.home_team) === selected || normalizeTeam(match.away_team) === selected,
  );
}

function buildTeamFilterOptions() {
  const available = getAvailableTeams();
  const options = [];
  if (state.myTeam) {
    options.push(`<option value="my-team" ${state.teamFilter === "my-team" ? "selected" : ""}>マイチーム</option>`);
  }
  options.push(`<option value="all" ${state.teamFilter === "all" ? "selected" : ""}>すべてのチーム</option>`);
  options.push(
    ...available.map(
      (team) =>
        `<option value="${escapeAttribute(team)}" ${state.teamFilter === team ? "selected" : ""}>${escapeHtml(displayTeam(team))}</option>`,
    ),
  );
  return options.join("");
}

function getPastSeasonMetadata(key) {
  const seasons = Array.isArray(state.data.pastIndex?.seasons) ? state.data.pastIndex.seasons : [];
  return seasons.find((season) => season.key === key) || null;
}

function buildPastSeasonOptions() {
  const seasons = Array.isArray(state.data.pastIndex?.seasons) ? state.data.pastIndex.seasons : [];
  return seasons
    .filter((season) => state.data.pastSeasons[season.key])
    .map(
      (season) =>
        `<option value="${escapeAttribute(season.key)}" ${state.pastSeason === season.key ? "selected" : ""}>${escapeHtml(
          season.short_label || season.label || season.key,
        )}</option>`,
    )
    .join("");
}

function bindPastSeasonFilter() {
  document.querySelector("#past-season-filter")?.addEventListener("change", (event) => {
    state.pastSeason = event.target.value;
    trackAnalytics("select_past_season", { season_key: state.pastSeason });
    renderPast();
  });
}

function renderPastCoverageNotice(season) {
  const note = season?.coverage?.note;
  if (!note) return "";
  return `
    <aside class="data-notice" aria-label="データ掲載範囲の注意">
      <strong>掲載範囲について</strong>
      <p>${escapeHtml(note)}</p>
    </aside>
  `;
}

function bindTeamFilter(selector) {
  document.querySelector(selector)?.addEventListener("change", (event) => {
    state.teamFilter = event.target.value;
    trackAnalytics("select_team_filter", {
      filter_area: selector.includes("past") ? "past" : "upcoming",
      team_filter: state.teamFilter,
    });
    render();
  });
}

function openTeamDialog() {
  const teams = getAvailableTeams();
  teamOptions.innerHTML = teams
    .map(
      (team) => `
        <button class="team-option ${team === state.myTeam ? "is-selected" : ""}" type="button" data-team="${escapeAttribute(team)}">
          ${teamLogo(team)}
          <span>${escapeHtml(displayTeam(team))}</span>
        </button>
      `,
    )
    .join("");
  teamOptions.querySelectorAll("[data-team]").forEach((button) => {
    button.addEventListener("click", () => saveMyTeam(button.dataset.team));
  });
  showDialog(teamDialog);
}

function saveMyTeam(team) {
  state.myTeam = team;
  state.teamFilter = "my-team";
  localStorage.setItem(TEAM_STORAGE_KEY, team);
  trackAnalytics("set_my_team", { team_code: team });
  closeDialog(teamDialog);
  renderMyTeamBanner();
  render();
}

function clearMyTeam() {
  const previousTeam = state.myTeam;
  state.myTeam = null;
  state.teamFilter = "all";
  localStorage.removeItem(TEAM_STORAGE_KEY);
  trackAnalytics("clear_my_team", { previous_team_code: previousTeam || "none" });
  renderMyTeamBanner();
  render();
}

function renderMyTeamBanner() {
  if (!state.myTeam) {
    myTeamBanner.hidden = true;
    return;
  }
  myTeamIdentity.innerHTML = `
    ${teamLogo(state.myTeam)}
    <span class="team-identity-copy">
      <span class="team-identity-label">マイチーム</span>
      <span class="team-identity-name">${escapeHtml(displayTeam(state.myTeam))}</span>
    </span>
  `;
  myTeamBanner.hidden = false;
}

function getAvailableTeams() {
  const values = new Set();
  safeMatches(state.data.upcoming).forEach((match) => {
    values.add(normalizeTeam(match.home_team));
    values.add(normalizeTeam(match.away_team));
  });
  if (!values.size && Array.isArray(state.data.standingsForecasts[0]?.teams)) {
    state.data.standingsForecasts[0].teams.forEach((team) =>
      values.add(normalizeTeam(team.team || team.team_name)),
    );
  }
  values.delete("tbd");
  values.delete("");
  return Array.from(values).sort((a, b) => displayTeam(a).localeCompare(displayTeam(b), "ja"));
}

function normalizeTeam(value) {
  const text = String(value ?? "").trim();
  return TEAM_NAME_TO_CODE[text] || text;
}

function displayTeam(value) {
  const code = normalizeTeam(value);
  return TEAM_NAMES[code] || String(value ?? "-");
}

function teamLogo(team) {
  const code = normalizeTeam(team);
  const cell = TEAM_EMBLEM_CELLS[code];
  const label = `${displayTeam(code)} ロゴ`;
  if (!cell) {
    return `<span class="team-logo is-fallback" role="img" aria-label="${escapeAttribute(label)}">⚽</span>`;
  }
  const [column, row] = cell;
  return `<span class="team-logo" role="img" aria-label="${escapeAttribute(label)}" style="background-position:${-(column * 40)}px ${-(row * 40)}px"></span>`;
}

function safeMatches(data) {
  return Array.isArray(data?.matches) ? data.matches : [];
}

function readStoredTeam() {
  try {
    return localStorage.getItem(TEAM_STORAGE_KEY);
  } catch {
    return null;
  }
}

function readStoredTheme() {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return ["system", "light", "dark"].includes(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

function formatScore(score) {
  if (!score || score.home == null || score.away == null) return "-";
  return `${score.home}-${score.away}`;
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${(number * 100).toFixed(1)}%`;
}

function formatNumber(value, digits = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(digits);
}

function formatDate(value) {
  if (!value) return "日程未定";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("ja-JP", {
    year: "numeric",
    month: "short",
    day: "numeric",
    weekday: "short",
  }).format(date);
}

function formatDateTime(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value ?? "-");
  return new Intl.DateTimeFormat("ja-JP", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatForecastDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value ?? "-");
  return new Intl.DateTimeFormat("ja-JP", {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatRankChange(value) {
  const change = Number(value);
  if (!Number.isFinite(change)) return "変動 -";
  if (change > 0) return `変動 ↑${change}`;
  if (change < 0) return `変動 ↓${Math.abs(change)}`;
  return "変動 →";
}

function renderEmptyState() {
  return document.querySelector("#empty-state-template").innerHTML;
}

function renderCurrentSeasonEmptyState() {
  return `
    <section class="empty-state">
      <div class="empty-icon">⚽</div>
      <h2>今シーズンの試合結果はまだありません</h2>
      <p>試合終了後に結果データが更新されると、予測との比較をここに表示します。</p>
    </section>
  `;
}

function renderError(error) {
  content.innerHTML = `
    <section class="empty-state error-panel">
      <div class="empty-icon">!</div>
      <h2>データを表示できません</h2>
      <p>${escapeHtml(error instanceof Error ? error.message : String(error))}</p>
      <button class="primary-button" type="button" onclick="window.location.reload()">再読み込み</button>
    </section>
  `;
}

async function requestAppInstall() {
  if (isInstalledApp()) return;
  trackAnalytics("install_attempt", {
    install_method: state.installPrompt ? "browser_prompt" : "manual_instructions",
  });
  if (state.installPrompt) {
    const prompt = state.installPrompt;
    await prompt.prompt();
    const choice = await prompt.userChoice;
    state.installPrompt = null;
    installButton.hidden = true;
    if (choice.outcome === "accepted") {
      state.installCompleted = true;
    }
    trackAnalytics("install_prompt_result", { outcome: choice.outcome });
    if (state.view === "settings") renderSettings();
    return;
  }
  showInstallInstructions();
}

function isInstalledApp() {
  return (
    state.installCompleted ||
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

function showInstallInstructions() {
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  trackAnalytics("install_instructions_open", {
    platform: ios ? "ios" : "other",
    prompt_available: Boolean(state.installPrompt),
  });
  if (state.installPrompt) {
    installInstructions.innerHTML = `
        <p class="dialog-copy">この端末では、下のボタンからアプリをホーム画面に追加できます。</p>
        <ol class="install-steps">
          <li><strong>「ホーム画面に追加」を押す</strong><span>ブラウザの確認画面が表示されます。</span></li>
          <li><strong>インストールを確定する</strong><span>追加後はホーム画面のアイコンから起動できます。</span></li>
        </ol>
      `;
    installDialogAction.hidden = false;
  } else if (ios) {
    installInstructions.innerHTML = `
        <p class="dialog-copy">iPhoneでは、Safariの共有メニューから追加します。</p>
        <ol class="install-steps">
          <li><strong>Safariでこのページを開く</strong><span>Safari以外で開いている場合は、URLをSafariで開き直してください。</span></li>
          <li><strong>共有ボタンを押す</strong><span>画面下部またはメニュー内の共有アイコンを選びます。</span></li>
          <li><strong>「ホーム画面に追加」を選ぶ</strong><span>「Webアプリとして開く」を有効にして「追加」を押します。</span></li>
        </ol>
      `;
    installDialogAction.hidden = true;
  } else {
    installInstructions.innerHTML = `
        <p class="dialog-copy">ブラウザのインストール機能がまだ利用できないため、メニューから追加してください。</p>
        <ol class="install-steps">
          <li><strong>ブラウザのメニューを開く</strong><span>Chromeでは画面右上のメニューを押します。</span></li>
          <li><strong>「アプリをインストール」を選ぶ</strong><span>表示されない場合は「ホーム画面に追加」を選択してください。</span></li>
        </ol>
      `;
    installDialogAction.hidden = true;
  }
  showDialog(installDialog);
}

function showDialog(dialog) {
  if (typeof dialog.showModal === "function") {
    if (!dialog.open) dialog.showModal();
  } else {
    dialog.setAttribute("open", "");
  }
}

function closeDialog(dialog) {
  if (typeof dialog.close === "function") {
    dialog.close();
  } else {
    dialog.removeAttribute("open");
  }
}

function selectNavigation(view) {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.view === view);
  });
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  try {
    await navigator.serviceWorker.register("./service-worker.js", { scope: "./" });
  } catch (error) {
    console.warn("Service Worker registration failed", error);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}
