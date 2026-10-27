# AI mobile experience

The authoritative integration, validation, package inventory and remaining device
acceptance are in [the final integration audit](final-ai-mobile-integration-audit.md).
This document describes the implementation. Earlier preparation and installation
states are historical Git revisions, not outstanding tasks.

## Entry points and artwork

The initial mobile Map overlays one 52 × 48 CSS pixel action containing the supplied
purple AI illustration, plus Tools. Its accessible name and tooltip are
“Planifier une aventure avec ChatGPT” / “Plan an adventure with ChatGPT”. Plan
retains the readable AI entry. Both open the same existing adventure dialog and
preserve its draft, endpoints, cancellation and focus return. Opening never starts
inference, routing or microphone recording.

The supplied `Downloads/image(10).png` is preserved byte for byte in
`assets/brand/sources/sugarglider-ai-planner-original.png`. The user explicitly
requested transparent-margin cropping for this AI illustration. Its proportional
256 × 194 transparent derivative is `assets/brand/sugarglider-ai-planner.png`, with
a byte-identical runtime copy. Source/output hashes and transformation details
remain in `assets/brand/README.md`. Only the optimized copy enters Android's
156-asset allowlist and the PWA shell. No original full-resolution image, remote
image dependency, replacement artwork or production-mascot modification is added.
The dialog header uses the same illustration.

The dialog prioritizes editable wishes, a 48 px microphone action, connected
ChatGPT status and the Generate adventure footer. Account management, spoken
language/provider, model/research/structured settings, endpoints and full
disclosures remain in secondary sections. The concise disclosure explains online
text/geographic-context processing; the full disclosure remains available.
Speech remains one explicit utterance with editable transcription and the existing
platform-provider disclosure. Routing, regional indexes and GPX remain local.

## Mobile layout and native tools

The bundled planner attaches its WebView below root-owned status/cutout insets;
root retains lateral, navigation and IME clearance. Native server/sharing chrome
remains only in its existing modes. Resume and renderer recovery retain their
existing lifecycle. The production launcher artwork is unchanged; staging adds
an XML TEST badge and uses **SG AI Test**, with compatible package/signing identity.

Tools contains language, Privacy, Map display, regional controls and App status.
The latter lazily reads actual packaged label, Git revision, variant and version.
It exposes no account identity or private paths. `show_privacy`, `get_app_identity`
and validated `set_ui_language` remain behind exact-origin, main-frame,
current-WebView, page-nonce and request-ledger gates. They provide no arbitrary
native command or URL execution.

Privacy retains the complete localized disclosure and the explicit published-policy
link. Its disclosure scrolls independently above vertically arranged, multiline
policy and Close actions. Android layout regressions verify that both actions and
the final disclosure paragraph remain reachable in French/English, at normal and
200% Android font scaling, including narrow portrait and landscape. The Activity
remains the localized context's base, preserving its window token.

See [mobile Map behavior](mobile-map-minimalism.md) for contextual editing,
compact attribution and the native-safe-area Tools height correction. Provider
attribution is retained, initially acknowledged for five seconds on compact maps,
and remains explicitly expandable. No raster tile prefetch or persistence is added.

## Language and canonical data

French is the default independently of Android/browser locale. Tools offers English
and remembers the validated `fr`/`en` preference in the existing PWA public-runtime
store. Missing, invalid or unreadable preferences fall back to French; failed
persistence is visibly session-only. Complete-message translation bindings update
the current document without Activity/WebView recreation.

User prose, geographical names, model stories, sources, licences, canonical request
values and GPX remain original. Access and potability enums such as `unknown` remain
wire values in both languages. Actual local-worker POI query and map preference
regressions cover this boundary. Language switching performs no routing, inference,
recording or location acquisition. Existing speech-provider/language choices remain
independent; a new explicitly submitted AI request receives the selected response
language instruction.

## Forest integration

PR #110 merged at `18b7dd726615b97293de00983c43985f268dfa64` from
`26c6dbe325333c48e2b7d5f126c165314f9a19ea`, and is already incorporated in this GUI
branch. It must not be cherry-picked or merged again. Its seven woodland runtime
files remain byte-identical to merged main. The shared results retain forest/history
tradeoff labels, shape gates and explanations with translations. Constraints,
profile identity, routed geometry, the shared 16-call budget and exact snapshot/GPX
serialization retain their existing owners. AI narratives do not create geometry.

## Authorized historical application cleanup

These eight exact audit applications were removed only after the user explicitly
authorized discarding each package's local data, under
`io.github.victorgabillon.sugarglider`:

- `.v2auditb1`, `.v2auditb2`, `.v2auditf1`, `.v2auditf2`
- `.v2auditn1`, `.v2auditn2`, `.v2auditn3`, `.v2auditp1`

Their APK identities and removal receipts are retained privately. This cleanup is
complete and must not be repeated. Production and canonical staging were neither
removed nor reset. `.debug`, `.v2debug`, `.placesrealdata` and eleven instrumentation
helpers remain; their unique data has not been authorized for deletion. Follow
[the audit ownership workflow](android-audit-workflow.md) for future disposable
installations. Never infer disposability from a suffix or display label.

## Evidence and device boundaries

Physical Fairphone editing, offline generation, GPX, supplied icon, AI controls,
launcher badge and attribution acceptance are complete on the installed 625ef8b
lineage; exact evidence and limitations are distinguished in the final audit.
Screenshots, full-state backups, APKs and private receipts remain outside Git.
A newly prepared APK does not imply permission to install it. Replacement requires
applicable authorization naming that artifact and fresh preservation checks.
Live ChatGPT inference requires separate authorization. No production replacement,
Google Play upload or public regional publication is part of this work.

## Named starting locations and all mobile tabs

The follow-up starts from merged GUI baseline `422e437` (PRs #110 and #111).
Endpoint lookup distinguishes missing descriptions, unresolved names, ambiguous
matches, coordinates outside the selected committed region, fixed-endpoint
conflicts, and failed graph arrival. A place name such as “Bastille” remains a
lookup request. Local exact matches use the existing Places index. Ambiguous
matches require selection; inferred endpoints still require review before routing.

An unresolved name offers an explicit **Search with IGN** action, disclosing that
only the place name goes to IGN Géoplateforme. It reuses the normal geocoder's
request limits, cancellation and credential-free transport. Selecting an outside
result reports missing coverage in the selected UI language and offers **View
regions**, which opens the existing manager. It does not select, install or download
a region, retry the model, or route online. The repository's Paris specification
does not establish that a usable Paris pack is installed. Existing selected points
require explicit release before a conflicting described location can replace them.
Completed search selections retain their provenance through exact saved-adventure
recovery, without another lookup or route calculation.

The available preserved Fairphone state contains the original Bastille request.
It does not establish the model's endpoint payload for that failed operation;
neither name-only nor out-of-region model coordinates are claimed as its observed
cause. No live inference, device installation, reset or application-data change is
needed for this follow-up's deterministic browser checks.

Mobile Map, Plan and Routes hide the permanent mascot/name in the shared toolbar.
The same AI action and Tools remain accessible; desktop branding and About remain.
The full-app browser driver captures all three tabs in French and English at
100% and 200% text, with a simulated 37 px Android top inset. It checks content
clearance, menu bounds, focus restoration, unchanged canonical route/editor/GPX,
and absence of automatic routing, inference or recording. Screenshots remain
outside Git. Native routing and model replies in these tests are synthetic;
browser screenshots are not new physical Fairphone acceptance.
