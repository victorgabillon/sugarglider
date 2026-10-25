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

Twenty-two focused JVM tests pass without live accounts or network dependencies,
including signed synthetic identities, tampering, scope reduction, refresh rotation,
account replacement rejection, cancellation before credential commit, sanitized HTTP
failures, stream truncation and encrypted-record integrity. Android Debug lint passes.
These results do not establish Android browser callback feasibility or live account
access. The exact-origin native bridge is wired, and the shared provider adapter receives
completed text, measured usage and actual web-search citations without credentials.
Page changes and inference backgrounding cancel owned work. Model output is never
a native command. Live inference remains unverified.

The strict proposal parser and local grounding adapter are also implemented and
covered by nineteen new browser scenarios plus the retained itinerary-import
harness. They reuse existing validation primitives and bounded leased Places
queries, preserve unresolved/ambiguous/outside/private outcomes, retain proposed
versus mapped/approach coordinates, and mark source URLs unverified unless a
completed research response actually cited them. The Waypoint producer now supports a bounded optional-stop insertion search for
loops and open routes, reusing its native validation and canonical publisher. A
single adventure session retains the region lease and shared 16-call gateway
across two 8-call rounds; exact anchors cannot change during revision. Checked
mapped approaches, explicit omissions, retained no-optional control and one-time
Nature enrichment are covered by 21 new routing scenarios across all six profiles.
The retained manual Waypoint and normal-planner harnesses pass. Twelve synthetic
request/result pairs (36 candidates) also pass Python canonical and neutral
submitted-candidate validation. This exposed and corrected a narrow mismatch in
the Python reconstruction of existing Near endpoint traversal anchors; 27 focused
Python tests and the existing endpoint browser suite pass.

These are synthetic routing tests, not real geographical acceptance. The deterministic assessment and two-call model controller are now implemented.
Fifteen new controller scenarios exercise the normal regional queries, shared
search/publisher and GPX path, including a measured additional checked stop after
revision, failed-revision retention, unknown surfaces/partial elevation, mandatory
confirmation, strict landmark arrival, changed region/intent and cancellation.
The controller sends a byte-bounded strategy/measurement summary without raw route
geometry, indexed regional records or full story prose. Model calls, measured
usage and native calls remain separately accounted. OSM categories support place
counts; a linked AI anecdote never becomes independently verified history. The
application retains both round snapshots and only chooses a revised portfolio
when supported measurements improve. AI route ordering puts measured distance-tolerance eligibility first. The
comparison route remains visible and leads within the same tolerance class;
optional-stop rewards alone cannot establish lower repetition or backtracking.
When only one alternative is requested, its comparison is also retained (at most
five published candidates). Manual Waypoint and Auto Tour ordering are unchanged.

The Android application now has a Plan with AI dialog with account/model controls,
text input, editable speech, explicit online-research/refinement choices, essential
required-place/destination review, progress and cancellation. An on-device speech
recognizer is preferred when available. Its microphone permission is requested
only for an explicit utterance. A platform speech fallback requires a native
provider-processing disclosure; its offline preference is not a guarantee.
Backgrounding the app stops its own recognizer. Native callbacks own their page
and operation, and late system results cannot become a later transcription.
Forty-eight focused JVM tests and Android Debug lint pass, including three speech
policy/protocol tests. Physical microphone behavior remains unverified.

Completed candidates use the existing native elevation client and sampling worker
in a bounded sequential batch. Matching retained results are reused across rounds;
cancellation drains native analysis and cancellation before releasing ownership.
Canonical candidates and GPX remain unchanged. Stories use plain text and explicit
safe HTTPS links; proposed points remain at their proposed or mapped coordinates,
and only checked arrivals receive reached styling. New AI stop names use the
matched local map name; conflicting mapped categories stay unresolved. Mapped
water potability remains distinct from access and arrival. The existing candidate controls,
terrain chart and native GPX saver use the selected canonical result.

The actual bundled application passes synthetic browser acceptance at phone and
desktop widths with verified OPFS components and real application workers. The test
connects a fake account, edits a transcription, generates and refines through the
normal native-message boundary, selects and exports exact GPX, retains a route after
a failed AI request, and restores the exact prior manual request/result/selection.
Seven dialog scenarios also cover enlarged text, required-place confirmation,
locally resolved End review and cancellation before region acquisition. Fifteen
retained/evolved elevation scenarios pass. The shell/Android allowlists include the
new modules under cache generation v107, with refreshed identities and CI steps.
All account, routing and terrain replies in these tests are explicitly synthetic.

Restart persistence, real Marly quality/latency, final comprehensive validation,
APK audit, review PR and separately authorized live/physical acceptance remain
outstanding. No AI APK has been installed or offered as complete.

## Official protocol references (checked 25 October 2026)

- [Registration and sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
- [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
- [Accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)

The documented OSS route uses system-browser registration, a stable host UUID and
an HTTP `127.0.0.1` callback. Account eligibility and Android feasibility must be
proved rather than inferred from desktop examples. Use the public Responses API
with `store: false`, `stream: true`; no backend-api endpoint or API-key fallback.
Model discovery does not itself prove web-search/Structured Outputs/tool support.

## Android speech references (checked 25 October 2026)

- [SpeechRecognizer](https://developer.android.com/reference/android/speech/SpeechRecognizer): on-device API, main-thread lifecycle and microphone permission.
- [RecognizerIntent](https://developer.android.com/reference/android/speech/RecognizerIntent): platform recognition and the advisory offline preference.
