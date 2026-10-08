// Acquisition data only. This module never reads planner state or calls routing.
export const LOCATION_RESULT_LIMIT = 6;
export class LocationSearchError extends Error {}
export function validateLocationQuery(value) {
  if (typeof value !== "string" || /[\u0000-\u001f\u007f-\u009f]/u.test(value)) {
    throw new LocationSearchError("Use plain search text without control characters.");
  }
  const query = value.trim();
  if (query.length < 3 || query.length > 200) throw new LocationSearchError("Enter between 3 and 200 characters.");
  return query;
}
export const normalizeLocationText = text => text.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().trim();
function text(value) {
  if (Array.isArray(value)) value = value.filter(item => typeof item === "string").join(", ");
  return typeof value === "string" ? value.replace(/[\u0000-\u001f\u007f-\u009f]/gu, " ").trim().slice(0, 200) : "";
}
export function normalizeOnlineLocations(document) {
  if (document?.type !== "FeatureCollection" || !Array.isArray(document.features) || document.features.length > 100) {
    throw new LocationSearchError("Online search returned an unreadable response. Try again later.");
  }
  const results = [];
  for (const feature of document.features) {
    const p = feature?.properties, coordinate = feature?.geometry?.coordinates;
    if (feature?.geometry?.type !== "Point" || !Array.isArray(coordinate) || coordinate.length !== 2) continue;
    const [lon, lat] = coordinate;
    const name = text(p?.toponym) || text(p?.name) || text(p?.label);
    if (!name || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) continue;
    const context = [text(p?.postcode), text(p?.city), text(p?.context), "France"].filter(Boolean).join(" · ");
    if (results.some(row => normalizeLocationText(row.name) === normalizeLocationText(name)
      && Math.abs(row.lat - lat) < 0.00005 && Math.abs(row.lon - lon) < 0.00005)) continue;
    results.push(Object.freeze({ name, secondaryLabel: context, lat, lon, source: "online" }));
    if (results.length === LOCATION_RESULT_LIMIT) break;
  }
  if (document.features.length && !results.length) {
    throw new LocationSearchError("Online search returned an unreadable response. Try again later.");
  }
  return Object.freeze(results);
}
function cancelled(signal) { signal?.throwIfAborted(); }
function wait(milliseconds, signal) {
  cancelled(signal);
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal?.removeEventListener("abort", abort); resolve(); }, milliseconds);
    signal?.addEventListener("abort", abort, { once: true });
  });
}
// One client per page. Cancellation settles the old fetch before a new one starts.
export function createLocationSearch({ config, localSearch, fetcher = fetch,
  online = () => navigator.onLine !== false, timeoutMs = 10_000, intervalMs = 1000 }) {
  let active = null, remoteTail = Promise.resolve(), nextRequestAt = 0;
  async function onlineResults(query, signal) {
    const settings = config();
    if (!settings?.available || settings.provider !== "ign_geoplateforme") {
      throw new LocationSearchError("Online address search is unavailable. You can still choose a point on the map.");
    }
    if (!online()) throw new LocationSearchError("Online address search is unavailable offline. You can still choose a point on the map.");
    let endpoint;
    try {
      endpoint = new URL(settings.endpoint);
      if (endpoint.protocol !== "https:" || endpoint.username || endpoint.password || endpoint.search || endpoint.hash) throw Error();
    } catch { throw new LocationSearchError("Online address search is unavailable. You can still choose a point on the map."); }
    await wait(Math.max(0, nextRequestAt - Date.now()), signal);
    cancelled(signal);
    endpoint.search = new URLSearchParams({ q: query, index: "address,poi", limit: String(LOCATION_RESULT_LIMIT) });
    const timeout = new AbortController();
    const timer = setTimeout(() => timeout.abort(), timeoutMs);
    nextRequestAt = Date.now() + intervalMs;
    try {
      const response = await fetcher(endpoint.href, { signal: AbortSignal.any([signal, timeout.signal]),
        headers: { Accept: "application/json" }, credentials: "omit", referrerPolicy: "no-referrer",
        redirect: "error", cache: "no-store" });
      cancelled(signal);
      if (response.status === 429) {
        const retry = Number(response.headers.get("Retry-After"));
        nextRequestAt = Date.now() + Math.max(5000, Number.isFinite(retry) ? Math.min(retry * 1000, 60_000) : 5000);
        throw new LocationSearchError("Online search is busy. Wait a moment before searching again.");
      }
      if (!response.ok) throw new LocationSearchError("Online search is unavailable. Try again later or choose on the map.");
      // Stream a bounded response; timeout covers decoding as well as headers.
      const reader = response.body.getReader(); const decoder = new TextDecoder("utf-8", { fatal: true });
      let size = 0, body = "";
      try {
        while (true) {
          const { done, value } = await reader.read();
          cancelled(signal);
          if (done) break;
          size += value.byteLength;
          if (size > 256 * 1024) throw new LocationSearchError("Online search returned an unreadable response. Try again later.");
          body += decoder.decode(value, { stream: true });
        }
        return normalizeOnlineLocations(JSON.parse(body + decoder.decode()));
      } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
    } catch (error) {
      cancelled(signal);
      if (timeout.signal.aborted) throw new LocationSearchError("Online search timed out. Try again or choose on the map.");
      if (error instanceof LocationSearchError) throw error;
      if (error instanceof SyntaxError || error instanceof TypeError && error.message.includes("encoded data")) {
        throw new LocationSearchError("Online search returned an unreadable response. Try again later.");
      }
      throw new LocationSearchError("Online search could not complete. Try again or choose on the map.");
    } finally { clearTimeout(timer); }
  }
  async function searchResolvedLocations(value, { signal: callerSignal, onLocal = () => {} } = {}) {
    const query = validateLocationQuery(value);
    active?.abort(); const controller = new AbortController(); active = controller;
    const signal = callerSignal ? AbortSignal.any([callerSignal, controller.signal]) : controller.signal;
    let local = [], localMessage = "No usable installed Places index. Choose a point on the map or search online.";
    const localTimeout = new AbortController(); const timer = setTimeout(() => localTimeout.abort(), 5000);
    try {
      const localSignal = AbortSignal.any([signal, localTimeout.signal]);
      // Optional storage/index work may hang: it must not hold online acquisition hostage.
      const response = await Promise.race([localSearch(query, localSignal), new Promise((_, reject) => {
        if (localSignal.aborted) reject(localSignal.reason);
        else localSignal.addEventListener("abort", () => reject(localSignal.reason), { once: true });
      })]);
      cancelled(signal);
      local = response.results.slice(0, LOCATION_RESULT_LIMIT);
      localMessage = response.available ? local.length ? "" : "No matching mapped places in the installed region." : localMessage;
    } catch (error) {
      cancelled(signal);
      if (error.code === "regional_selection_required") localMessage = "Choose an installed region to search its mapped places.";
    } finally { clearTimeout(timer); }
    cancelled(signal); onLocal({ results: local, message: localMessage });
    const operation = remoteTail.catch(() => {}).then(() => { cancelled(signal); return onlineResults(query, signal); });
    remoteTail = operation.catch(() => {});
    try {
      const onlineRows = await operation; cancelled(signal);
      const remote = onlineRows.filter(row => !local.some(place => normalizeLocationText(place.name) === normalizeLocationText(row.name)
        && Math.abs(place.lat - row.lat) < 0.00005 && Math.abs(place.lon - row.lon) < 0.00005)).slice(0, 8 - local.length);
      return { local, localMessage, remote, remoteMessage: remote.length ? "" : "No online results. Try adding a town name." };
    } catch (error) {
      cancelled(signal);
      return { local, localMessage, remote: [], remoteMessage: error.message };
    } finally { if (active === controller) active = null; }
  }
  return Object.freeze({ searchResolvedLocations });
}
