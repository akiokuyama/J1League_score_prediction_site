(() => {
  "use strict";

  const MEASUREMENT_ID = "G-D757SHS30N";
  const CONSENT_STORAGE_KEY = "j1_analytics_consent_v1";
  const LINKED_DOMAINS = [
    "akiokuyama.github.io",
    "j1league-score-prediction.streamlit.app",
  ];
  const VALID_CONSENT = new Set(["granted", "denied"]);
  const sentEventKeys = new Set();
  let configured = false;
  let tagRequested = false;

  window.dataLayer = window.dataLayer || [];
  window.gtag =
    window.gtag ||
    function gtag() {
      window.dataLayer.push(arguments);
    };

  window.gtag("consent", "default", {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    analytics_storage: "denied",
    wait_for_update: 500,
  });

  function readConsent() {
    try {
      const value = window.localStorage.getItem(CONSENT_STORAGE_KEY);
      return VALID_CONSENT.has(value) ? value : null;
    } catch {
      return null;
    }
  }

  function persistConsent(value) {
    try {
      window.localStorage.setItem(CONSENT_STORAGE_KEY, value);
    } catch {
      // 保存領域を利用できない場合も、現在のページでは選択を反映します。
    }
  }

  function applyConsent(value, { persist = true } = {}) {
    if (!VALID_CONSENT.has(value)) return;
    if (persist) persistConsent(value);
    window.gtag("consent", "update", {
      ad_storage: "denied",
      ad_user_data: "denied",
      ad_personalization: "denied",
      analytics_storage: value,
    });
    if (value === "granted") ensureGoogleTag();
    updateConsentUi(value);
    window.dispatchEvent(
      new CustomEvent("j1analyticsconsentchange", { detail: { consent: value } }),
    );
  }

  function ensureGoogleTag() {
    if (!tagRequested) {
      tagRequested = true;
      const script = document.createElement("script");
      script.async = true;
      script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(MEASUREMENT_ID)}`;
      script.dataset.j1AnalyticsTag = MEASUREMENT_ID;
      document.head.appendChild(script);
    }
    if (!configured) {
      configured = true;
      window.gtag("js", new Date());
      window.gtag("set", "linker", { domains: LINKED_DOMAINS });
      window.gtag("config", MEASUREMENT_ID, {
        debug_mode: ["localhost", "127.0.0.1"].includes(window.location.hostname),
      });
    }
  }

  function sanitizeParameters(parameters) {
    return Object.fromEntries(
      Object.entries(parameters || {})
        .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value))
        .map(([key, value]) => [key, typeof value === "string" ? value.slice(0, 100) : value]),
    );
  }

  function track(eventName, parameters = {}) {
    if (readConsent() !== "granted") return false;
    ensureGoogleTag();
    window.gtag("event", eventName, sanitizeParameters(parameters));
    return true;
  }

  function trackOnce(eventName, parameters = {}, eventKey = eventName) {
    if (sentEventKeys.has(eventKey)) return false;
    if (!track(eventName, parameters)) return false;
    sentEventKeys.add(eventKey);
    return true;
  }

  function consentLabel(value) {
    if (value === "granted") return "許可中";
    if (value === "denied") return "停止中";
    return "未選択";
  }

  function updateConsentUi(value = readConsent()) {
    document.querySelectorAll("[data-analytics-consent-status]").forEach((element) => {
      element.textContent = consentLabel(value);
    });
    document.querySelectorAll("[data-analytics-consent]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.analyticsConsent === value));
    });
    const banner = document.querySelector("[data-analytics-consent-banner]");
    if (banner) banner.hidden = value !== null;
  }

  function renderConsentBanner() {
    if (document.querySelector("[data-analytics-consent-banner]")) return;
    const banner = document.createElement("aside");
    banner.className = "analytics-consent-banner";
    banner.dataset.analyticsConsentBanner = "";
    banner.setAttribute("aria-label", "利用状況データの設定");
    banner.innerHTML = `
      <div class="analytics-consent-copy">
        <strong>利用状況データについて</strong>
        <p>
          サービス改善のため、同意いただいた場合のみGoogle Analyticsで画面表示や操作を計測します。
          個人を直接特定する情報は送信しません。
        </p>
      </div>
      <div class="analytics-consent-actions">
        <button type="button" class="analytics-consent-button analytics-consent-deny" data-analytics-consent="denied">
          今は許可しない
        </button>
        <button type="button" class="analytics-consent-button analytics-consent-allow" data-analytics-consent="granted">
          許可する
        </button>
      </div>
    `;
    document.body.appendChild(banner);
    updateConsentUi();
  }

  function bindConsentControls(root = document) {
    root.querySelectorAll("[data-analytics-consent]").forEach((button) => {
      if (button.dataset.analyticsConsentBound === "true") return;
      button.dataset.analyticsConsentBound = "true";
      button.addEventListener("click", () => {
        const previous = readConsent();
        const next = button.dataset.analyticsConsent;
        applyConsent(next);
        if (next === "granted") {
          track("analytics_consent_update", {
            consent_state: next,
            previous_state: previous || "unset",
          });
        }
      });
    });
  }

  function bindTrackedLinks(root = document) {
    root.querySelectorAll("[data-analytics-event]").forEach((link) => {
      if (link.dataset.analyticsEventBound === "true") return;
      link.dataset.analyticsEventBound = "true";
      link.addEventListener("click", () => {
        const parameters = {};
        for (const [key, value] of Object.entries(link.dataset)) {
          if (key.startsWith("analyticsParam")) {
            const rawName = key.slice("analyticsParam".length);
            const name = rawName
              .replace(/^[A-Z]/, (character) => character.toLowerCase())
              .replace(/[A-Z]/g, (character) => `_${character.toLowerCase()}`);
            parameters[name] = value;
          }
        }
        track(link.dataset.analyticsEvent, parameters);
      });
    });
  }

  function initialize() {
    const storedConsent = readConsent();
    if (storedConsent) applyConsent(storedConsent, { persist: false });
    renderConsentBanner();
    bindConsentControls();
    bindTrackedLinks();
    updateConsentUi(storedConsent);
  }

  window.J1Analytics = Object.freeze({
    measurementId: MEASUREMENT_ID,
    linkedDomains: [...LINKED_DOMAINS],
    getConsent: readConsent,
    setConsent: applyConsent,
    bindConsentControls,
    bindTrackedLinks,
    track,
    trackOnce,
    updateConsentUi,
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
