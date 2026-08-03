export function excludedShellPath(pathname) {
  return pathname.startsWith("/v1/")
    || pathname.startsWith("/v2/")
    || pathname === "/openapi.json"
    || pathname === "/docs"
    || pathname.startsWith("/docs/")
    || pathname === "/redoc"
    || pathname.startsWith("/redoc/")
    || pathname === "/manifest.webmanifest"
    || pathname === "/service-worker.js"
    || pathname.endsWith(".gpx")
    || pathname.endsWith("/events")
    || pathname.includes("/events/")
    || pathname.endsWith("/live")
    || pathname.includes("/live/");
}

export function classifyShellRequest(request, origin) {
  if (request.method !== "GET") return "ignore";
  if (hasSensitiveHeaders(request.headers)) return "ignore";
  const url = new URL(request.url);
  if (url.origin !== origin || excludedShellPath(url.pathname)) {
    return "ignore";
  }
  if (request.mode === "navigate") return "navigation";
  if (url.pathname.startsWith("/static/") && url.search === "") {
    return "static";
  }
  return "ignore";
}

export function createCurrentCacheAccess(cacheStorage, cacheName) {
  const currentCache = () => cacheStorage.open(cacheName);
  return {
    match: (request) => currentCache().then((cache) => cache.match(request)),
    put: (request, response) => currentCache().then(
      (cache) => cache.put(request, response),
    ),
  };
}

export function networkFirstNavigation(
  request,
  {
    fetchRequest,
    matchRootShell,
    fallbackResponse,
  },
) {
  return fetchRequest(request).catch(() => matchRootShell().then(
    (cached) => cached ?? fallbackResponse(),
  ));
}

export function cacheFirstStatic(
  request,
  {
    matchRequest,
    fetchRequest,
    storeResponse,
  },
) {
  return matchRequest(request).then((cached) => {
    if (cached) return cached;
    return fetchRequest(request).then((response) => {
      if (!response.ok || response.type !== "basic") return response;
      return Promise.resolve()
        .then(() => storeResponse(request, response.clone()))
        .catch(() => {})
        .then(() => response);
    });
  });
}

const SENSITIVE_HEADERS = Object.freeze([
  "authorization",
  "cookie",
  "x-sugarglider-participant-token",
  "x-sugarglider-outing-owner-token",
  "x-sugarglider-outing-join-token",
  "x-saved-route-owner-token",
]);

function hasSensitiveHeaders(headers) {
  if (!headers) return false;
  if (typeof headers.has === "function") {
    return SENSITIVE_HEADERS.some((name) => headers.has(name));
  }
  const names = Object.keys(headers).map((name) => name.toLowerCase());
  return SENSITIVE_HEADERS.some((name) => names.includes(name));
}
