const APP_CACHE = "j1-prediction-app-v10";
const DATA_CACHE = "j1-prediction-data-v1";

const APP_SHELL = [
  "./",
  "./index.html",
  "./styles.css?v=5",
  "./app.js?v=8",
  "./manifest.webmanifest",
  "./data/past_prediction_results/index.json",
  "./data/past_prediction_results/2026_27_j1.json",
  "./data/past_prediction_results/2026_special.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(APP_CACHE).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => ![APP_CACHE, DATA_CACHE].includes(key))
            .map((key) => caches.delete(key)),
        ),
      ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  const isPredictionData =
    (url.hostname === "raw.githubusercontent.com" &&
      url.pathname.includes("/J1League_score_prediction_site/") &&
      url.pathname.includes("/outputs/")) ||
    (url.origin === self.location.origin &&
      url.pathname.includes("/app/data/past_prediction_results/") &&
      url.pathname.endsWith(".json"));

  if (isPredictionData) {
    event.respondWith(networkFirst(request, DATA_CACHE));
    return;
  }

  if (url.origin === self.location.origin) {
    event.respondWith(staleWhileRevalidate(request, APP_CACHE));
  }
});

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw new Error("Prediction data is unavailable offline.");
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const networkPromise = fetch(request)
    .then((response) => {
      if (response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => null);
  if (cached) {
    networkPromise.catch(() => null);
    return cached;
  }
  const networkResponse = await networkPromise;
  return networkResponse || cache.match("./index.html");
}
