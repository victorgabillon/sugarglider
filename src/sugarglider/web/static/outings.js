import { ApiError } from "./api.js";

const SLUG_PATTERN = "[A-Za-z0-9_-]{20,64}";

async function outingError(response) {
  let body;
  try { body = await response.json(); } catch { body = null; }
  const error = body?.error;
  return new ApiError(
    error?.message ?? `The server returned HTTP ${response.status}.`,
    JSON.stringify({
      status: response.status,
      code: error?.code ?? "outing_error",
    }, null, 2),
    error?.code ?? "outing_error",
  );
}

export function outingSlug(pathname = window.location.pathname) {
  const match = pathname.match(new RegExp(`^/o/(${SLUG_PATTERN})/?$`));
  return match?.[1] ?? null;
}

export function captureOutingInviteToken(location = window.location, historyObject = window.history) {
  const parameters = new URLSearchParams(location.hash.replace(/^#/, ""));
  const token = parameters.get("invite");
  if (location.hash) {
    historyObject.replaceState(
      historyObject.state,
      "",
      `${location.pathname}${location.search}`,
    );
  }
  return token && token.length >= 32 && token.length <= 128 ? token : null;
}

export function parseSavedRouteReference(value, origin = window.location.origin) {
  const input = String(value ?? "").trim();
  if (new RegExp(`^${SLUG_PATTERN}$`).test(input)) return input;
  let url;
  try { url = new URL(input, origin); } catch { return null; }
  if (url.origin !== origin || url.search || url.hash) return null;
  const match = url.pathname.match(new RegExp(`^/r/(${SLUG_PATTERN})/?$`));
  return match?.[1] ?? null;
}

export async function createOuting(
  title,
  displayName,
  savedRouteSlug,
  avatarKey = "blue",
) {
  const response = await fetch("/v2/outings", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      schema_version: 1,
      title,
      participant_display_name: displayName,
      participant_avatar_key: avatarKey,
      saved_route_slug: savedRouteSlug,
    }),
  });
  if (!response.ok) throw await outingError(response);
  return response.json();
}

export async function getOuting(slug) {
  const response = await fetch(`/v2/outings/${encodeURIComponent(slug)}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw await outingError(response);
  return response.json();
}

export async function joinOuting(
  slug,
  token,
  displayName,
  savedRouteSlug,
  avatarKey = "blue",
) {
  const response = await fetch(
    `/v2/outings/${encodeURIComponent(slug)}/participants`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Sugarglider-Outing-Join-Token": token,
      },
      body: JSON.stringify({
        schema_version: 1,
        display_name: displayName,
        avatar_key: avatarKey,
        saved_route_slug: savedRouteSlug,
      }),
    },
  );
  if (!response.ok) throw await outingError(response);
  return response.json();
}

export async function deleteOuting(slug, ownerToken) {
  const response = await fetch(`/v2/outings/${encodeURIComponent(slug)}`, {
    method: "DELETE",
    headers: { "X-Sugarglider-Outing-Owner-Token": ownerToken },
  });
  if (!response.ok) throw await outingError(response);
}

export async function leaveOuting(slug, participantId, participantToken) {
  const response = await fetch(
    `/v2/outings/${encodeURIComponent(slug)}/participants/${encodeURIComponent(participantId)}`,
    {
      method: "DELETE",
      headers: { "X-Sugarglider-Participant-Token": participantToken },
    },
  );
  if (!response.ok) throw await outingError(response);
}

export async function downloadOutingParticipantGpx(slug, participantId) {
  const response = await fetch(
    `/v2/outings/${encodeURIComponent(slug)}/participants/${encodeURIComponent(participantId)}/gpx`,
    { headers: { Accept: "application/gpx+xml" } },
  );
  if (!response.ok) throw await outingError(response);
  return {
    blob: await response.blob(),
    filename: attachmentFilename(
      response.headers.get("Content-Disposition"),
    ),
  };
}

export function publicOutingUrl(outing) {
  return new URL(
    outing.share_path ?? `/o/${outing.slug}`,
    window.location.origin,
  ).href;
}

export function outingInviteUrl(receipt) {
  return new URL(
    receipt.invite_path ?? `/o/${receipt.slug}#invite=${receipt.join_token}`,
    window.location.origin,
  ).href;
}

export async function shareOutingInvitation(receipt) {
  if (typeof navigator.share !== "function") {
    throw new ApiError(
      "Sharing is unavailable in this browser. Copy the invitation link instead.",
      "",
      "outing_share_unavailable",
    );
  }
  await navigator.share({
    title: receipt.title ?? "Sugarglider outing",
    text: "Join this Sugarglider outing with your own independently planned route.",
    url: outingInviteUrl(receipt),
  });
}

function attachmentFilename(header) {
  const match = header?.match(/filename="?([^";]+)"?/i);
  return match?.[1] ?? "sugarglider-participant-route.gpx";
}
