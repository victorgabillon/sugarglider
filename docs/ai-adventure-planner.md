# AI Adventure Planner — implementation in progress

This milestone is not released or complete. The existing manual planner and
itinerary importer remain available. No AI credentials or device installations
are part of the development checkpoints below.

## Architecture decisions

Native Android owns ChatGPT authorization, credentials, model discovery, network
requests and speech transcription. The exact-origin main-frame bridge carries
bounded application operations and validated results, never OAuth credentials.
The shared web application owns proposal validation, grounding, bounded local
search, deterministic assessment, story presentation and canonical GPX export.
No additional server or second router is introduced.

One AI operation owns its account, region/build identity, cancellation and UI
lifetime. Model output is untrusted data. The current selected route remains
untouched until a complete validated adventure result is committed explicitly.
A failed refinement retains the first valid results. One initial model request
and at most one model revision are allowed; routing uses one bounded cached
request context rather than resetting budgets for each proposed stop subset.

Model-suggested stops default optional. Mandatory intent requires explicit user
authority. Grounding preserves proposed and locally corroborated coordinates,
uncertainty, access status and source provenance separately. Routing/snapping
and validated arrival determine outcomes, never map proximity or a model claim.
Nature, distance and elevation are measured; unavailable surface/repetition/access
metrics remain unknown. Model narratives never become geometry or GPX extensions.

## Work packages

1. **A: native ChatGPT connection.** Implement the documented dynamic registration,
   loopback listener, PKCE, signature/claim verification, encrypted per-registration
   credentials, refresh rotation, sign-out and account switching. Discover models
   using the selected account; accept only completed bounded Responses streams.
2. **B: adventure proposal.** Extend shared input-validation helpers where useful;
   one strict bounded proposal with intent, wishes, optional/mandatory suggestions,
   unresolved coordinates and source-labelled stories. Central tested instructions.
3. **C: grounding and local routing.** Reuse leased Places queries and existing mode
   producers/evaluator. Extend the smallest routing owner needed to consider arbitrary
   optional targets alongside exact mandatory anchors, with deterministic bounded
   subset/order proposals, the existing strict cached native budgets and truthful
   visited/approached/omitted outcomes. Retain a no-optional control.
4. **D: assessment and one revision.** Reuse measured metrics, validity gates and
   canonical publication. Send compact disclosed measurements, not raw geometry,
   to a single optional model revision. Compare measured outcomes deterministically.
5. **E: application experience.** Text and editable speech, account/model controls,
   progress/clarification, story inspection, current authoritative route and GPX.
   Investigate focused immutable local snapshot persistence through the existing
   PWA store, without another IndexedDB opener or rerouting on restoration.
6. **F: integration.** Deterministic synthetic model plus actual local planner tests,
   private geographical acceptance, full checks once integrated, then draft PR.
   Build/audit staging; installation and live account consent require separate
   explicit user actions. Preserve the existing 23.172 km selection and all regions.

## Current checkpoint

The native connection core now includes a temporary loopback listener, exact callback
transactions, RS256 signature/issuer/audience/time/nonce validation, encrypted atomic
account records in no-backup Android storage, separate registration identities,
refresh rotation, sign-out and per-operation cancellation. All network endpoints
are fixed official HTTPS destinations; redirects and custom TLS trust are absent.
The ID-token algorithm/endpoints were checked against live issuer discovery metadata.

Nineteen focused JVM tests pass without live accounts or network dependencies,
including signed synthetic identities, tampering, scope reduction, refresh rotation,
account replacement rejection, cancellation before credential commit, sanitized HTTP
failures, stream truncation and encrypted-record integrity. Android Debug lint passes.
These results do not establish Android browser callback feasibility or live account
access. MainActivity/bridge wiring, model usage/citation metadata, UI and live inference
remain outstanding. No AI feature has been installed or offered as working yet.

## Official protocol references (checked 25 October 2026)

- [Registration and sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
- [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
- [Accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)

The documented OSS route uses system-browser registration, a stable host UUID and
an HTTP `127.0.0.1` callback. Account eligibility and Android feasibility must be
proved rather than inferred from desktop examples. Use the public Responses API
with `store: false`, `stream: true`; no backend-api endpoint or API-key fallback.
Model discovery does not itself prove web-search/Structured Outputs/tool support.
