# AI Adventure authentication review — 26 October 2026

This is a focused source review and deterministic regression assessment for PR
#110, continuing commit `7760936`. It is not a third-party security audit or a
claim that physical sign-in exercises every credential lifecycle. The previous
Fairphone acceptance establishes actual authorization, signed identity validation,
model discovery and completed research; live refresh and remote revocation still
need separately authorized testing.

## Reviewed boundaries

| Boundary | Findings |
| --- | --- |
| OAuth transaction | `ChatGptAuthorization` generates separate 256-bit state, nonce and verifier, uses S256 PKCE, exact issued registration and callback, rejects duplicate/unexpected parameters, checks issuer and consumes the transaction once. Browser lifetime is 180 seconds. |
| Loopback listener | `ChatGptLoopback` binds IPv4 127.0.0.1 on a random port. Peer, Host including port, method and callback path are checked; request bytes, attempts and socket waits are bounded. State/PKCE authenticate the redirect; an HTTP Origin header is not treated as identity. The socket closes after receipt, cancellation and finalization. |
| Tokens and identity | Fixed official token/discovery/JWKS endpoints, no redirect following or custom trust. RS256 signature, unique trusted key, issuer, audience/authorized party, expiry, issue/not-before time, nonce and subject are checked. Token-provided URLs are never fetched. Token response requires Bearer and bounded expiry; inference requires both plan-use scopes. |
| Protected storage | Native AES-GCM records use an Android Keystore key, atomic files in no-backup storage, bounded decoding and client-ID/filename binding. Account identity cannot be replaced under an existing registration. No raw credentials enter the bridge or browser persistence. Hardware-backed key attestation was not established. |
| Refresh and sign-out | Refresh rotation retains subject/client continuity and respects current operation ownership before commit. Switching cancels owned work and clears the model catalog. Sign-out blocks local use before remote revocation, clears credentials and reports unconfirmed remote revocation. Interruption after server-side refresh rotation can require reconnection; no weakened identity retry is added. Physical refresh/revocation remains untested in this follow-up. |
| Native bridge | Exact configured origin, current WebView, main frame, page/channel ledger and navigation/account epochs are required. Inference requires a visible Activity. Backgrounding cancels inference; destruction closes owned resources. No `addJavascriptInterface` or wildcard origin is added. Bundled application code remains trusted to initiate disclosed account usage. |
| Transport | Fixed HTTPS endpoints, platform TLS, no cookies/retries/alternate billing path. Only a bounded, completed SSE response can be accepted. Absent Responses MIME retains the earlier observed exception; explicit wrong MIME, truncated streams, incomplete items and terminal failures remain rejected. |
| Deadline correction | Explicit close yields `cancelled`; the unchanged 120-second shared network deadline yields `deadline`; a socket timeout before that deadline yields `network_timeout`. Remaining time bounds socket/connect waits, post-read completion is checked and every attached connection disconnects in `finally`. Sanitized diagnostics contain enums/counts/durations, never exception text or provider bodies. |
| Model output | Strict bounded proposals and stories remain untrusted data. Local identity, approach and route validation own feasibility. Stories cannot add stops, invoke native operations, modify geometry or enter GPX. Hosted-search source metadata and response citations retain distinct provenance, with HTTPS/size/deduplication checks; neither verifies claim support. Story-only responses must preserve requested reached-place IDs and locally resolved OSM IDs. Links require explicit HTTPS navigation and retain safe text rendering and opener protections. Citation matching does not verify claims. |
| Disclosure | Explicit Generate shares the description, retained endpoints/exact points and at most 24 mapped public place records. Optional revision shares compact measurements and place identities; story research uses reached identities and response-language context. Complete packs, routed geometry and GPX remain local. No new hosted discovery dependency is added. |
| Speech | User action and provider disclosure remain mandatory. Remembering the provider stores only schema version and an enum in the existing PWA store; restoration never records audio or grants consent. French native disclosure explains potential provider processing. Dictation stays editable, foreground and bounded. |
| Production build | Release debugging remains disabled; staging is intentionally debuggable and isolated. No background microphone/location permission, background service, model endpoint override, production signing or deployment change is introduced. APK manifests/assets are audited separately. |

## Residual limits

No new blocking credential or bridge defect was identified in this review.
Successful physical authentication alone is not a complete independent security
review. Live refresh rotation, expired authorization, account switching and remote
sign-out still need physical lifecycle evidence; no credential extraction is
authorized to obtain it. Debug staging requires the existing trusted-device
development conditions.

The provider preview rejects server output-token/tool caps. The client keeps its
existing time, stream, research and two-request bounds; these are not billing
ceilings. Account/model capabilities remain discovered rather than hardcoded.
See the [official preview contract](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations),
[accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)
and [completed streaming events](https://developers.openai.com/api/reference/resources/responses/streaming-events).

Keep PR #110 draft until the remaining product/physical acceptance and required
CI checks are satisfactory. This review authorizes neither installation nor
production publication.
