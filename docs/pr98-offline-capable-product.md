# PR98: offline-capable Android product and release gates

Product direction approved for this work: **Option A, offline-capable route planning**.
Implementation base: main `45a31c8789e00476652c90f75a2e323f4e69ee51`.
PR97 is an unmerged draft at `d891d263888efc664409b56d12e70bacd8255dd7`;
none of its source changes are merged or cherry-picked into PR98. Its
[final report](https://github.com/victorgabillon/sugarglider/blob/d891d263888efc664409b56d12e70bacd8255dd7/docs/pr97-webview-autofill-privacy.md)
and diagnostic findings remain historical evidence. This branch continues to
support main's original strict planner UID diagnostic and PR97's branch.

## Product guarantee

> After downloading a supported region, Sugarglider calculates routes, displays regional maps, analyzes elevation and exports GPX on the device without requiring an internet connection.

The supported area must cover the request. Maps, routing and regional indexes must
be installed and verified; V2 installation requires all five components, including
elevation. Routing never substitutes a server, a straight line or another region
for unavailable coverage. Missing height samples remain unknown. Selected-route
elevation failure is explicit and does not weaken routing or invent zero heights.
D+/D− are terrain estimates affected by DEM accuracy, sampling and filtering;
they are not surveyed measurements. There is no turn-by-turn navigation guarantee
or guarantee of legal access, current trail condition, safety or rideability.

Downloading, updating and checking remote regional files requires connectivity;
local integrity/readiness verification uses installed bytes. The bundled catalog
is local. Opening the region screen is not permission to download a region.
Optional online address search is enabled in the current package, sends submitted
text to IGN Géoplateforme, and is separate from offline Places search/planning.
GPX Save uses the user's chosen Android document provider, which may be remote or
sync files. Social sharing, outings and live-location publication remain disabled
by the fixed packaged policy; retained implementation code is not an enabled feature.

## Three independent assessments

| Gate | Required evidence | Effect on acceptance |
| --- | --- | --- |
| A: offline functionality | Verified installed region; six profiles; waypoint open routes/loops and Auto Tour; local maps/Places/Nature; native IGN heights, D+/D− and chart; selection, cancellation, Save and restart; missing-data failures | GO only within the tested region/device/control scope. Zero platform bytes are not a prerequisite. |
| B: first-party network controls | No hidden routing-server fallback, automatic route/location upload or unintended remote API; only explicit installer downloads; accurate optional-action disclosure and local-only capability guards | Remains required independently of A. Platform attribution is not an exemption for first-party behavior. |
| C: Android/WebView diagnostic | Exact available monotonic UID counters, all nonzero findings, known Autofill origin and unknown residual traffic retained | A nonzero zero-byte diagnostic stays **failed**. Platform privacy disclosure is **REVIEW REQUIRED**, even if another short window is silent. |

PR97 observed 34 complete controls: 23 nonzero failures and 11 silent windows across
different conditions, not a statistical failure rate. Actual View exclusion,
autocomplete-off, hidden forms and metrics opt-out did not establish a supported
privacy fix. Ordinary and numeric-only controls reached
`content-autofill.googleapis.com`. No-form/no-script/no-assets traffic also
reproduced without DevTools; its source is unknown. Encrypted payload contents,
personal-information presence/absence and provider retention were not established.
Do not dismiss these communications as harmless, subtract their bytes, or rename a
failed diagnostic as passed. PR95/96/97 acceptance conclusions are not edited here;
PR98 records the deliberate new product criterion separately.

### Receipts

`python -m sugarglider.offline_regions.offline_acceptance receipt.json` validates
bounded metadata-only evidence and deterministically produces separate results.
All named checks are required; booleans/counters are strict, unavailable or reset
counters are rejected, and extra fields such as route coordinates or approval flags
are rejected. A connected control with an available server cannot establish offline
capability. The validator checks consistency, not the truth of submitted observations;
raw test logs and actual test execution remain necessary. It never authorizes release.

| Experimental condition | What it establishes | What it does not establish |
| --- | --- | --- |
| Region server unavailable | Installed-data operations do not need that host | Other networking or the entire device is disconnected |
| Research WebView network loads blocked | WebView network denial can coexist with tested intercepted local assets and local workflows | Native download clients, browser services or other UIDs are blocked |
| Research APK without Internet permission | The tested app runs with that permission absent; component downloads are unavailable in that build | A normal downloadable production build has the same permission policy, or the phone is disconnected |
| Actually disconnected device | Operations work under the recorded device-wide disconnection | All future devices, regions and platform versions work |

Do not change phone-wide connectivity, DNS, VPN, certificates, Autofill or security
settings for these tests. Full physical disconnection needs separate explicit user
authorization. Narrower tests must retain their narrower names. A zero-byte receipt
under denial is not a new platform privacy fix.

## V1 publication versus V2 preparation

The live policy, read on 19 October 2026, explicitly describes version 1.0.2/code 4
with an effective date of 16 September 2026. The repository's
`deploy/regions/github-pages/privacy/index.html` is an older placeholder template,
not a byte-identical copy of that published page. Neither is replaced by this PR.
The installed production package reports version 1.2.0/code 8; that fact alone does
not identify its full source or approve this V2 runtime. Current unreleased main
also retains code 8 / version 1.2.0. No version or signing change is made here.

The bundled public catalog still references V1 build `902f951b…`; V2 requires five
components and rejects incompatible V1 readiness while retaining old files. The
private verified IGN Yvelines build is
`a92396de46a6fed5fa1a49fc8c939c39bc6371424aa90c9b71f237878294c7fd`.
It has **no public publication authorization**. Its explicit IGN69 height reference
must not become EGM96. Licence evidence is not operator approval; the current
Copernicus-specific public approval gate deliberately rejects this IGN component.
`publication_allowed` stays false; no public artifacts/catalog are changed.

## Coordinated release prerequisites

1. Publisher reviews the [V2 policy draft](pr98-privacy-policy-draft.md),
   [Data Safety matrix](pr98-data-safety-review.md), platform communications and
   unresolved payload/retention/declaration questions. Confirm identity, contact,
   target audience, approved hosts and final policy URL/date. No Play form is submitted.
2. Complete the IGN/combined-data publication review: pinned originals, source
   vintages, IGN69 transformation/void behavior, accurate IGN/OSM attribution,
   Licence Ouverte and ODbL/derived graph obligations, downstream notices and
   immutable component/build identities. Do not infer approval from source access.
3. Only after explicit publication authorization, implement a reviewed IGN-aware
   publication gate with regression coverage. Rebuild or explicitly identify any
   changed immutable manifest; reverify all five components, size/hash agreement
   and catalog entries. Do not flip the existing private flag or bypass the gate.
4. Stage the compatible app and complete immutable V2 files/catalog privately.
   Confirm old V1 data retention, V2 installation/restart, update/recovery and all
   six profiles. Plan rollout ordering/rollback so the new app is never offered
   only incompatible V1 downloads. Existing public V1 files remain immutable.
5. Obtain additional measured lower-RAM-device acceptance, installation storage
   headroom and actual physical 16 KiB-page-size acceptance. Static APK/ELF alignment
   and the Fairphone's 4 KiB execution do not establish 16 KiB runtime support.
6. Review the exact final Release APK, permissions, bundled public assets, no private
   CA/DEM/test code, HTTPS, source attribution and social-disabled policy. Complete
   A/B/C review on release-representative devices. Platform disclosure remains
   required under the approved offline contract.
7. Confirm the highest version code in every relevant Play track and obtain a
   publisher-approved higher code for the future V2 artifact; the currently retained
   code 8 is not a new-upload authorization. Separately authorize coordinated
   data/catalog/policy publication and Android version/signing/Play rollout. This PR grants none of those actions or approvals.

PR96's bounded installer worker and streamed Places/Nature validation are unchanged.
PR97 measured approximately 867 MB installation/activation and 1.30 GB broader UI
aggregate PSS, with protocol-specific overhead and substantial cleanup reduction.
These are observations, not universal safe limits or a leak finding. This work does
not initiate a separate memory redesign or claim certification of smaller devices.

See [PR98 execution and acceptance](pr98-offline-acceptance.md) for measured results,
limitations, preservation and independent final decisions.
