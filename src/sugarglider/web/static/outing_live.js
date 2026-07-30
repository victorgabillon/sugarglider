import { ApiError } from "./api.js";

const PARTICIPANT_TOKEN_HEADER = "X-Sugarglider-Participant-Token";

async function liveError(response) {
  let body;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const error = body?.error;
  return new ApiError(
    error?.message ?? `The server returned HTTP ${response.status}.`,
    JSON.stringify({
      status: response.status,
      code: error?.code ?? "outing_live_error",
    }, null, 2),
    error?.code ?? "outing_live_error",
    { status: response.status },
  );
}

export async function getOutingLiveSnapshot(slug, options = {}) {
  const response = await fetch(
    `/v2/outings/${encodeURIComponent(slug)}/live`,
    {
      headers: { Accept: "application/json" },
      signal: options.signal,
    },
  );
  if (!response.ok) throw await liveError(response);
  return response.json();
}

export async function publishOutingPosition(
  slug,
  participantId,
  participantToken,
  payload,
  options = {},
) {
  const response = await fetch(
    `/v2/outings/${encodeURIComponent(slug)}/participants/${encodeURIComponent(participantId)}/position`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        [PARTICIPANT_TOKEN_HEADER]: participantToken,
      },
      body: JSON.stringify(payload),
      signal: options.signal,
    },
  );
  if (!response.ok) throw await liveError(response);
  return response.json();
}

export async function clearOutingPosition(
  slug,
  participantId,
  participantToken,
  options = {},
) {
  const request = {
    method: "DELETE",
    headers: { [PARTICIPANT_TOKEN_HEADER]: participantToken },
    keepalive: options.keepalive === true,
  };
  if (options.signal) request.signal = options.signal;
  const response = await fetch(
    `/v2/outings/${encodeURIComponent(slug)}/participants/${encodeURIComponent(participantId)}/position`,
    request,
  );
  if (!response.ok) throw await liveError(response);
}

export function connectOutingLiveEvents(slug, handlers) {
  const path = `/v2/outings/${encodeURIComponent(slug)}/events`;
  const source = new EventSource(path);
  let intentionallyClosed = false;

  source.addEventListener("open", () => {
    handlers.open?.();
  });
  source.addEventListener("error", () => {
    if (intentionallyClosed) return;
    if (source.readyState === EventSource.CLOSED) {
      handlers.closed?.();
    } else {
      handlers.reconnecting?.();
    }
  });

  addJsonListener(source, "snapshot", "cursor", handlers.snapshot, handlers);
  addJsonListener(source, "reset", "cursor", handlers.reset, handlers);
  addJsonListener(
    source,
    "position_updated",
    "event_id",
    handlers.positionUpdated,
    handlers,
  );
  addJsonListener(
    source,
    "position_cleared",
    "event_id",
    handlers.positionCleared,
    handlers,
  );
  source.addEventListener("outing_closed", (event) => {
    const payload = parseJson(event.data);
    if (!payload || Object.keys(payload).length !== 0) {
      handlers.malformed?.();
      return;
    }
    handlers.outingClosed?.();
  });

  return {
    close() {
      if (intentionallyClosed) return;
      intentionallyClosed = true;
      source.close();
      handlers.closed?.();
    },
  };
}

function addJsonListener(source, name, identifierField, handler, handlers) {
  source.addEventListener(name, (event) => {
    const payload = parseJson(event.data);
    if (
      !payload
      || !identifierMatches(event.lastEventId, payload[identifierField])
    ) {
      handlers.malformed?.();
      return;
    }
    handler?.(payload, event.lastEventId);
  });
}

function parseJson(value) {
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed
      : null;
  } catch {
    return null;
  }
}

function identifierMatches(lastEventId, payloadIdentifier) {
  return Number.isSafeInteger(payloadIdentifier)
    && payloadIdentifier >= 0
    && (
      !lastEventId
      || (/^[0-9]+$/.test(lastEventId)
        && Number(lastEventId) === payloadIdentifier)
    );
}
