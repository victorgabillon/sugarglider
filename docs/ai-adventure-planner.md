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
Nature enrichment are covered by 27 new routing scenarios across all six profiles.
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
Distance eligibility and outside-distance pressure precede soft wishes. In
strategy comparison, jointly measured loop shape precedes Nature and other soft
wishes; missing shape never becomes a fabricated zero penalty. Optional subset
search retains its bounded place reward behind the existing hard loop-shape
screens, without promoting over the comparison on unknown repetition.
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
new modules under cache generation v108, with refreshed identities and CI steps.
All account, routing and terrain replies in these tests are explicitly synthetic.

A private read-only host benchmark now exercises the existing Marly/Yvelines graph,
Places, Nature and IGN height files through this pipeline. It uses a curated
geographic model fixture, not a live account. It exposed overlong random proposal
corridors. AI search now orders proposal corridors by bounded insertion estimates
for locally checked places and reuses Auto Tour’s bounded measured-distance
correction. Exact anchors and the real target remain fixed; the unchanged 8-call
round and 16-call operation limits still apply. These estimates never establish
route distance, geometry or landmark arrival. Repeated actual routes, canonical
validation, clean selected GPX and file integrity are checked privately. Routes
share corridors. AI loop retention now reuses Auto Tour’s sampled native-line
diversity proxy to omit near-identical optional loops, while always exposing the
comparison. The UI explains fewer suitable options when the bounded search cannot
provide the requested count. This is not an exact graph-overlap measurement. Surface, access and exact repetition remain unknown.

Exact latest-adventure recovery now uses one record in the existing optional PWA
store. A disposable worker bounds and hashes the record, validates request,
canonical identities/traversal, strict arrivals, measured assessments and bound
elevation, then restores the unchanged result and selection. Both actual round
records and stories are preserved; no search history is fabricated. No model,
routing or terrain request is made to restore. Startup offers an explicit Reopen
saved adventure action, keeping the editable planner independent. Missing regions
remain unavailable for new planning. The UI reports failed persistence and offers
Forget; clearing saved offline data drains pending writes before removing data.
No database migration, additional store opener or credential persistence is added.
Nine storage scenarios and the actual bundled app at mobile/desktop sizes cover
reload/GPX identity, missing region, stale recovery after editing and clear/forget.

Final local verification passes: Python 3.13 `make check` (1,612 tests, Ruff and
strict mypy), all 61 browser harness pages, 18 self-contained browser acceptance
drivers, Debug/Release JVM tests (268/263), both Android lints and APK assembly.
The staging APK audit checks all 153 exact shell assets, unchanged native routing,
existing staging certificate and 16 KiB alignment. Six older visual drivers that
require a running six-profile server and retained real-map setup were not run;
their component harnesses are included in the 61 passing pages. The private HTTPS
regional contract suite also passes with synthetic publication authorization only.

The repeated read-only Marly host benchmark retains two actual graph-derived
options: a 36.787 km comparison and a 37.830 km historical option with four checked
stops. The latter has 37.564% mapped woodland, 30.801% urban, 26.275% unknown and
413 m ascent/descent. One measured revision improves loop shape while trading off
woodland. The alternatives share approximately 76.9% of exact coordinate segments;
this is not an edge-ID overlap measurement. Sixteen native route calls and fewer
than 1.51 million Nature operations stay within the existing budgets. The model
fixture is curated, not live AI; the height and routing measurements are real host
measurements. This does not establish three independent predominantly forest loops.

Draft review, GitHub CI and separately authorized live/physical acceptance remain
outstanding. Android loopback sign-in, account eligibility, completed inference,
research/schema capabilities, microphone behavior and phone latency remain
unverified. No AI APK has been installed or offered as complete. Authentication
must not be merged on synthetic evidence alone.

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

## Inference and local-search capability boundary

The account-specific model catalog establishes visibility, not tool eligibility.
The current [ChatGPT plan-sharing preview contract](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
requires an input message array and rejects `max_output_tokens` and
`max_tool_calls`. Those fields are omitted. The client owns a 120 s network
operation, 15 s socket-read timeout, 2 Mi-character stream, 256 Ki-character
event and 64 Ki-character completed-text limits (the proposal additionally has a
64 KiB UTF-8 limit). Research is aborted when a fifth distinct hosted search is
observed, and a completion containing more than four searches is rejected.
These are client acceptance/transport limits, not a server-side token or billing
cap: work may already be running when cancellation is observed. There remain at
most two model requests for an adventure. Incomplete output is rejected.
Unsupported optional research/schema can be disabled explicitly; text mode still
supplies the complete schema as instructions and applies the same strict local
validation. There is no automatic retry onto another billing route.

[Responses API fields](https://developers.openai.com/api/reference/python/resources/responses/methods/create)
and [tool use](https://developers.openai.com/api/docs/guides/tools) document hosted
and client function mechanisms. That general documentation does not establish
that an eligible ChatGPT account/model grants each tool. No live account has yet
proved research, strict schema or function tools. The first implementation uses
bounded local Places queries after the proposal; it does not ship a model-driven
client-function loop or upload the index. Such a loop would consume response
continuations and needs an observed account capability plus an explicit budget;
it must not silently consume the single strategy-revision allowance.

## First physical sign-in attempt

After a separately authorized staging update, the user reported browser sign-in
success, but the app reported a connection failure and retained no account.
Installed regions, offline native routing and the exact original manual route
remain valid. This is not proof of an account-eligibility failure or completed
Android authentication.

Review found two recovery defects: the 120-second HTTP deadline started before
up to 180 seconds of browser authorization, and the issued registration ID could
be lost when fetching identity metadata failed. HTTP timing now starts at the
first network request and stays shared across subsequent requests. The browser
phase remains bounded separately; its bridge timeout covers both phases. The
issued public registration is retained before subsequent network work, while
credentials still require full signed identity validation. Native status also
exposes a memory-only diagnostic containing fixed failure-kind/stage/network-cause
enums. It includes no exception messages, provider bodies, URLs, headers or tokens.
These fixes and diagnostics require a new audited staging artifact and authorized
physical retest; the cause of the first observed failure remains unproven.

A subsequent authorized physical retest confirmed that the callback reached the
app and retained its public registration, then failed at identity discovery with
`network_cause: dns`. Public DNS probes under the staging UID succeeded in the
foreground; one background probe returned unknown host. A later warm-cache
background probe succeeded, so this is not evidence of a universal DNS outage.
Post-callback networking was starting while Firefox was still foreground.
Completion now waits on the connection executor for this Activity to resume before
fetching metadata or exchanging tokens. Callback receipt and return share the
remaining bounded browser phase; cancellation and destruction release the wait,
and the callback socket closes immediately after receipt. No network settings,
TLS trust, endpoints, permissions or secret fallback are changed. A live retest
is still required to establish that this resolves the observed connection failure.

On the foreground-handoff build, real native sign-in completed: signed identity
validation passed, the account was retained in protected native storage and plan
usage was granted. Model discovery then failed at the HTTP decoding boundary;
no inference had started. The catalog now has a separate 1 MiB input bound for
provider metadata, with identity/token documents retaining their 256 KiB cap.
Native diagnostics distinguish media type, size, JSON and catalog-schema failures
without recording provider bodies, and report the catalog's observed byte count.
The app still exposes only the ordered visible slug/label list, with at most 100
entries and no hardcoded model or alternate-format fallback. Physical retest must
establish whether the previous size bound caused this observed catalog failure.

On the catalog build, the protected account survived installation and eight real
models loaded from a 610,824-byte catalog, confirming the old 256 KiB size limit.
Two explicit phone operations (research on, then off) were rejected before a
completed response. Review of the current preview limitations identified two
unsupported request fields and the required array input. These are corrected;
this correction still requires separately authorized physical verification.
Diagnostics retain only allowlisted rejection codes and parameter names plus
HTTP status, with unknown provider values replaced by `other`. No provider body,
message, request headers or credentials cross that boundary.

The separately authorized request-format build passed all four CI workflows and
retained the connected account. Two normal physical requests (research/schema on,
then both off) passed HTTP admission but failed media-type validation. A further
diagnostic attempt inspected only HTTP status and null checks under the debugger:
the real response was HTTP 200 with no Content-Type header. No response body,
credential, account label or raw HTTP traffic was captured; the debugger was
detached and the original route restored. Responses alone may now omit that
header, but must still pass bounded SSE framing and terminal completion. Explicit
conflicting media types and missing identity/token media types remain rejected.
Transport-level regressions cover declared/missing SSE media type, HTML, JSON,
partial deltas and identity-document rejection. Completed live inference remains
unproved until the corrected build is separately authorized and tested.
