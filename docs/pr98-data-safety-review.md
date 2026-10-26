# PR98: Google Play Data Safety evidence — DRAFT, NOT SUBMITTED

Reviewed 19 October 2026 against current official guidance. This is technical
preparation for the V2 offline-capable Android candidate, not a completed Play form,
legal approval or a statement about the live Play Console. The final publisher
must resolve the open rows using the exact distributed artifact and provider facts.

## Official rules used for this review

Google's [Data Safety guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)
covers off-device transmissions by app code, SDKs and app-controlled WebViews;
bundled application content is not ordinary open-web browsing. Local-only
processing is treated differently. Ephemeral off-device processing still needs
form review. A user-directed transfer or qualifying service-provider relationship
can change sharing treatment; it does not automatically remove collection duties.
IP-derived location must be considered if actually inferred. Provider role,
retention and inference must not be guessed from HTTPS or an endpoint name.

The [User Data policy](https://support.google.com/googleplay/android-developer/answer/10144311?hl=en)
requires accurate disclosures and an accessible privacy policy identifying the app
or relevant publisher. Data use beyond reasonable user expectations may require
prominent disclosure/consent review. A short Privacy dialog, new product wording
or absence of first-party analytics is not by itself compliance approval.

[Android's WebView privacy documentation](https://developer.android.com/develop/ui/views/layout/webapps/webview-privacy)
describes usage/crash reporting and per-app statistics opt-out. It does not identify
PR97's encrypted payloads or make an Autofill/offline-privacy guarantee. PR97's
metrics-opt-out control still produced traffic. No security feature or platform
setting is disabled in this work.

## Evidence and proposed declaration treatment

“Proposed” below means a working review position. **REVIEW REQUIRED** is not a
submitted yes/no response. Do not export this matrix as a completed Console form.

| Data/flow | Confirmed first-party/package behavior | Proposed treatment / unresolved questions |
| --- | --- | --- |
| Precise/approximate device location | Coarse/fine permissions; private foreground position, precise grant needed for a fix; prior grant can resume on reopen; page hide suspends watch; manual planning survives denial | On-device first-party positioning alone is not an off-device collection claim. Review Android/location-provider processing separately. No background location or enabled live upload. Do not infer all location-related traffic is absent. |
| Planned routes, waypoints, terrain analysis, local Places/Nature | Native Valhalla plus installed files/local workers; no configured routing-server fallback, automatic route POST or social publication | Proposed: no first-party routing/social backend collection during the tested ordinary workflow. Export destinations and unknown platform payloads prevent extending this to a blanket app-wide answer. |
| Trail nickname, badge and preferences | Local storage; no enabled social account or outings; form fields may participate in WebView processing | Proposed: local first-party storage. Whether WebView sends any field-related personal information is unknown; do not assume local storage settles all off-device handling. |
| Imported GPX | User selects a file; local inspection; no first-party import upload | Proposed: local processing. Document-provider retrieval may itself use a cloud connection controlled by that provider. |
| Exported GPX / files and documents | Explicit canonical GPX generation and Android document selection; destination may sync | User-initiated sharing treatment needs publisher review under the actual flow. Review collection separately; do not promise deletion or encryption practices for arbitrary destinations. |
| Regional HTTPS downloads | Explicit installer action, immutable manifests/components, no route/location body; host receives IP/file/client metadata | Identify approved V2 hosts and their actual purposes, retention, IDs and any IP-location inference. Do not assume the host qualifies as a service provider, ephemeral processor or anonymous recipient. |
| Optional IGN address search | Only explicit Search/Enter submits `q`, index and limit to `data.geopf.fr`; no first-party device fix or whole route attached; connection metadata also reaches provider | Proposed collection review for submitted search text, possibly address/location information supplied by the user. App-functionality purpose and optionality of this first-party action are supported; retention, onward use, provider role and precise data categories require review. |
| Published policy / attribution links | Explicit external-browser action; current policy describes an earlier release | Disclose the external action and relevant providers. Do not silently deploy the new draft or describe the old page as V2-approved. |
| Google WebView Autofill | PR97 identifies `content-autofill.googleapis.com` from ordinary, numeric and real application forms before typing/routing; tested hints do not eliminate it | **REVIEW REQUIRED:** payload fields, data types, purposes, provider role, retention, disclosure/consent and optionality. Do not declare collected route coordinates, and do not declare no personal information, from origin-only evidence. The open-web exception is not automatically applicable to bundled app-controlled content. |
| Residual platform/UID traffic | Repeated no-form controls have positive bytes, including without DevTools; some are silent | **REVIEW REQUIRED:** initiator, recipient, payload, identifiers and purpose remain unknown. Keep exact failed zero-byte diagnostics. No “harmless” or “analytics” attribution is established. |
| Advertising / analytics dependencies | Audited first-party Gradle/web dependencies contain no ads/analytics SDK; no AD_ID permission; no first-party analytics endpoint identified | Proposed: no first-party ad/analytics integration. Review transitive artifacts and provider reporting; this does not settle WebView/platform data declarations. |
| Device/app identifiers, diagnostics and crashes | Not intentionally uploaded by first-party planning; Android/WebView may have provider behavior outside page-resource observation | **REVIEW REQUIRED** using provider-specific facts. Missing Advertising ID permission does not prove absence of every identifier or diagnostic flow. |
| Social membership / live location | Fixed `V1ReleasePolicy` rejects sharing origins/messages; no sharing service, deep link, notification or background-location permission in the manifest; bundled config disables social | Proposed: no collection through enabled social/live functionality. Retained source modules are not a declaration of enabled features. Future activation requires a new review. |
| Encryption in transit | Production app blocks cleartext; installer and explicit IGN client use HTTPS without redirects/credentials; local intercepted origin has no remote fallback | Proposed supported first-party transports are encrypted. Whole-app/global answer remains a review item for provider flows and user-selected transfers. TLS does not establish end-to-end encryption or anonymity. |
| Storage/deletion/account management | Private app storage and OPFS; region removal; app backup/transfer excluded; Android app-data removal; no social account; exports remain destination-controlled | Document exact controls. No provider/server deletion API or retention promise is established for hosting/platform recipients. No Sugarglider social account exists. Optional ChatGPT connection, local sign out and attempted remote revocation now require the additional review below; do not imply deletion of the external ChatGPT account. |

## Package/source checks

Normal Debug/Release retain Internet, coarse/fine location and explicit speech-input microphone permission; there is no
background-location, location-FGS, notification, advertising-ID or broad-storage
permission. Android Save uses a user-selected document URI. Source anchors:
`MainActivity`, `V1ReleasePolicy`, `BundledShellPolicy`, `NativeRuntime`,
`RegionalRoutingDownloader`, `GpxDocumentSave`, `planner_location.js`,
`location_search.js`, `local_planner.js`, `regional_planning.js`, `region_product.js`
and `android_ui_config.json`. Exact compiled package/dependency verification and
physical observations are in [PR98 acceptance](pr98-offline-acceptance.md).

App/region data, phone connectivity, signing, version and production catalog are
not changed to obtain a declaration answer. Any research no-Internet APK is an
explicit diagnostic and cannot replace the normal package's permissions or facts.

## Publisher decisions still required

1. Confirm the final V2 publisher/controller/contact and publishable policy text,
   effective date and URL. Existing public identity/contact are historical evidence,
   not permission to approve this draft automatically.
2. Resolve provider and unknown-flow questions above, including the Google provider
   behavior on supported Android versions. Determine whether further prominent
   disclosure or consent is necessary; the product-contract change does not settle it.
3. Confirm static host/IGN query retention, metadata processing, provider roles and
   any location inference. No provider retention or special exemption is assumed.
4. Classify actual data types, purposes, optionality, collection versus sharing,
   encryption and deletion using final implementation/provider evidence. A blanket
   no-data-collected/no-data-shared answer is **not approved** by this work.
5. Review all active distribution artifacts/tracks and target-audience requirements;
   do not assume a candidate's technical report describes the live store declaration.
6. Obtain explicit coordinated policy/data/catalog/Android release authorization.
   No Play Console declaration, draft form, upload or release is submitted here.

## Comparison with existing documents

The live policy is approved HTML scoped to version 1.0.2/code 4. It already explains
on-device planning, foreground location, GitHub connection metadata and GPX storage
providers, and disables social publication. It does not document the V2 IGN terrain
pipeline, current optional IGN geocoding or PR97's measured Autofill/residual findings.
The tracked deploy HTML is an older unapproved placeholder/social template and must
not be confused with that live page. `code4-privacy-policy-proposed.md` and
`pr44-privacy-data-safety.md` remain historical proposals. This PR adds a separate
[V2 draft](pr98-privacy-policy-draft.md); it neither rewrites those records nor
copies a new page into the deployment directory.

## AI Adventure Planner delta — REVIEW REQUIRED, NOT SUBMITTED

| Added flow | Verified implementation | Remaining publisher/provider review |
| --- | --- | --- |
| Optional ChatGPT authorization | System-browser OAuth; per-install registration/host UUID; encrypted native credentials; narrow public account status in the UI; no OAuth tokens in browser storage or adventure snapshots | Review account identity/identifier processing by OpenAI, supported account terms, retention, purposes and roles. No live account or Android callback acceptance has yet been demonstrated. Local Sign out is not external account deletion. |
| Description and chosen planning locations | Explicit Generate submits description/edited transcript, chosen Start/End, exact anchors, activity and regional bounds to OpenAI; optional second request submits a bounded strategy/measured summary, not raw geometry or the private graph/index | Review submitted text and location-related data categories, optionality, functionality purposes, disclosure and provider processing. Do not declare universally no off-device data. No declaration is accepted on the publisher’s behalf. |
| Optional research | Enabled only by the disclosed research choice; selected account/model may receive hosted web-search tools; capped tool work and two total model requests | Verify actual eligible-account capability and relevant provider/subprocessor behavior. General API documentation does not prove each model/account has tools. No live research evidence exists yet. |
| Speech | RECORD_AUDIO only for explicit on-device recognition when available; separate disclosed platform recognition fallback can process audio online; transcript is editable before Generate | Verify physical recognizer/provider behavior and review applicable audio/text declaration treatment. An offline preference is not proof that the provider keeps audio local. No raw audio file or first-party model audio upload is implemented. |
| Latest adventure recovery | One bounded local result/selection/stories/source record in existing optional storage; no raw prompt input field, native OAuth credential, ChatGPT account/email metadata or live-position history; model text may repeat user-supplied details; explicit Reopen, Forget and existing clear controls | Include these user-chosen places and model interpretation in local-storage disclosure. Exported copies/provider retention are separate. Optional browser storage is not a durability guarantee. |

The pre-existing WebView/platform unknowns remain unresolved. These additions do
not authorize Google Play answers, a new public policy, an effective date or a
release. The current public policy URL and availability remain unchanged.
