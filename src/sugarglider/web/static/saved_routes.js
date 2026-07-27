import { ApiError } from "./api.js";

async function savedRouteError(response) {
  let body;
  try { body = await response.json(); } catch { body = null; }
  const error = body?.error;
  return new ApiError(
    error?.message ?? `The server returned HTTP ${response.status}.`,
    JSON.stringify({
      status: response.status,
      code: error?.code ?? "saved_route_error",
    }, null, 2),
    error?.code ?? "saved_route_error",
  );
}

export function sharedRouteSlug(pathname = window.location.pathname) {
  const match = pathname.match(/^\/r\/([A-Za-z0-9_-]{20,64})\/?$/);
  return match?.[1] ?? null;
}

export async function createSavedRoute(sourceRequest, candidate) {
  const response = await fetch("/v2/saved-routes", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      schema_version: 1,
      source_request: sourceRequest,
      candidate,
    }),
  });
  if (!response.ok) throw await savedRouteError(response);
  return response.json();
}

export async function getSavedRoute(slug) {
  const response = await fetch(`/v2/saved-routes/${encodeURIComponent(slug)}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw await savedRouteError(response);
  return response.json();
}

export async function deleteSavedRoute(slug, ownerToken) {
  if (!ownerToken) {
    throw new ApiError(
      "This browser does not hold the deletion capability for this saved route.",
      "",
      "saved_route_owner_token_missing",
    );
  }
  const response = await fetch(`/v2/saved-routes/${encodeURIComponent(slug)}`, {
    method: "DELETE",
    headers: { "X-Saved-Route-Owner-Token": ownerToken },
  });
  if (!response.ok) throw await savedRouteError(response);
}

export function savedRouteShareUrl(saved) {
  return new URL(
    saved.share_path ?? `/r/${saved.slug}`,
    window.location.origin,
  ).href;
}

export async function shareSavedRoute(saved) {
  if (typeof navigator.share !== "function") {
    throw new ApiError(
      "Sharing is not available in this browser. Copy the link instead.",
      "",
      "saved_route_share_unavailable",
    );
  }
  const url = savedRouteShareUrl(saved);
  await navigator.share({
    title: saved.route_name ?? "Sugarglider route",
    text: "View this immutable Sugarglider route snapshot.",
    url,
  });
}

export async function downloadSavedRouteGpx(slug) {
  const response = await fetch(
    `/v2/saved-routes/${encodeURIComponent(slug)}/gpx`,
    { headers: { Accept: "application/gpx+xml" } },
  );
  if (!response.ok) throw await savedRouteError(response);
  return {
    blob: await response.blob(),
    filename: attachmentFilename(
      response.headers.get("Content-Disposition"),
    ),
  };
}

function attachmentFilename(header) {
  const match = header?.match(/filename="?([^";]+)"?/i);
  return match?.[1] ?? "sugarglider-route.gpx";
}
