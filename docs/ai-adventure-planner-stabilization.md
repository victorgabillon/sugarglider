# AI Adventure Planner stabilization — 26 October 2026

This report records the earlier ea746cf/88bdb8c stabilization milestone. The
subsequent [woodland route-quality report](ai-adventure-route-quality.md) supersedes
its search/selection description and draft-status conclusion. Its physical
measurements remain historical evidence; the newer algorithm has not been
installed on the Fairphone.

PR #110 continues on `feat/ai-adventure-integration` in its existing isolated
worktree, from `7760936`. The original workspace, private regional data, staging
data and selected user route are preserved. Separately authorized staging updates
retain app data. The latest physical run establishes three distance-feasible
geometry families, improved latency versus the preceding exact-request run and
three source-linked reached-place anecdotes. This milestone remains draft:
three good forest/history alternatives are still not physically accepted.

## Request reliability and measurements

The original physical evidence recorded 59.084 s initial inference, 41.543 s
refinement, 19,276 input / 3,442 output tokens and approximately 106 s end to end.
The refinement did not improve that actual route set. A later explicit-three
request encountered a network read timeout and, on the user's retry, the 120 s
deadline; neither attempt reached routing.

The native call now distinguishes `cancelled`, `network_timeout` and `deadline`.
The shared network deadline remains 120 seconds, socket reads remain bounded by
15 seconds and connect waits by 10 seconds, shortened by remaining time. Deadline
and socket failures do not claim the user pressed Cancel. Auth expiry, usage
limits, unsupported capability and invalid/incomplete responses retain separate
outcomes. A completion arriving after expiry is rejected and owned connections
disconnect on every outcome. Deterministic JVM and browser regressions cover
these distinctions, non-disclosure and valid-first-result retention.

Native whitelisted measurements include request byte count, response-header
latency, first semantic event/text latency, observed web-research event span,
stream duration and completed output character count. Missing observations are
null. Research span is not a claim about provider-internal reasoning/tool time.
The controller additionally measures context/input preparation, local structured
validation, grounding, native routing, Nature, publication, elevation, optional
refinement and total time. Some timings are inclusive and must not be summed.
Total time can include endpoint/mandatory-place review. Usage retains only the
provider's numeric input/output/total token fields. No telemetry upload or log of
credentials, private coordinates, conversations or raw model output was added.

Planning instructions shrink from 3,952 to 3,203 characters (19%). They ask for
four to eight useful places, short stories and focused research of identifiable
mapped places. Routing-preference interpretation alone does not need research.
Strict output validation, source limitations and account-discovered model choice
remain. No unsupported token/tool caps or hardcoded model are introduced.

The optional second call is skipped for a satisfactory measured set. When routes
need work, it retains the existing bounded strategy revision. When the set is
satisfactory but reached places lack sourced anecdotes, a smaller stories-only
contract researches those reached identities without routing again. Every story
must retain its locally resolved OSM identity. Failed/malformed research preserves
the first valid routes and narratives. The limit remains two model requests.
Publishing a provisional result before refinement was deliberately left out of
this change to preserve the existing atomic result/recovery transition.

The separately authorized [c84048d physical acceptance](ai-adventure-fairphone-stabilization-acceptance.md)
completed the exact French request: 104.462 s initial, 41.969 s second call,
44,520 tokens and 152.017 s total. This is worse than the previous observation,
not a latency success. GPX/restart equality passed and the original route was
restored. The follow-up now makes the initial historical-planning pass without
research or anecdotes, then prioritizes checked reached identities for final
research. Identity-bound source improvements survive a rejected route strategy.
The separately authorized ea746cf follow-up completed two real calls in
60.346 s and 65.008 s, with 28,106 tokens and 130.968 s total. Against c84048d's
same typed request, end-to-end time decreased 13.8% and token use 36.9%. This is a
single observed comparison, not a general latency guarantee; the earlier
two-alternative voice run was faster overall and used fewer tokens. Initial
research is now absent, final research observes 17 source URLs, and three of four
selected visits have source-linked anecdotes. Full timings, route-quality limits
and exact GPX/restart checks are in the linked physical report.

## Alternative count and real graph experiment

French/English route-count phrases are interpreted locally before inference.
Explicit two and three remain two and three even if the model changes its count;
an unspecified count defaults to three. Place counts do not become route counts.
The existing one-option comparison exception remains explicit. Exact/manual
constraints, profile identity, checked arrival and graph-derived geometry remain
unchanged.

The search uses the same 8+8 cached route-call budget. It explores a bounded set
of useful control headings and measured distance corrections, tries small place
groups, retains isolated single-place probes and avoids spending every attempt
on one insertion branch. Only complete finalists receive Nature; the existing
request cache reuses repeated enrichment. At most five finalists per round are
enriched, rather than enriching temporary insertion states. Hard distance and
loop-shape gates remain ahead of measured nature preferences.

The acceptance experiment uses deterministic proposals with the existing private
Marly graph, Places, Nature and IGN elevation. Model answers are curated fixtures,
**not live ChatGPT**. Valhalla runs read-only with networking disabled on the host,
not through the physical Android wrapper. No dataset is rebuilt or modified.

| Retained line | Native distance | Error from 35 km | Checked places | Woodland | Urban | Unknown | D+ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No-POI comparison | 35.831 km | 0.831 km | 0 | 15.6% | 41.0% | 25.2% | 382.50 m |
| Historical detour variant | 37.432 km | 2.432 km | 3 | 17.5% | 38.6% | 26.5% | 389.75 m |
| Other route family | 37.184 km | 2.184 km | 1 | 42.0% | 30.6% | 21.9% | 390.25 m |

All three lines meet the fixture's ±3 km tolerance. The first two share about
87.8% of the detour's exact coordinate-segment length. They are retained as useful
comparison variants and **do not count as two independent route families**.
The third shares approximately 6.3%/10.3% with those lines. These are geometry
proxies, not exact routed edge IDs, repetition or parallel-corridor equivalence.

The product now combines its existing sampled native-line diversity proxy with
an 85% mutual exact-coordinate-segment sharing check when reporting loop families.
It retains the no-POI control and labels its close detour as a comparison variant.
The UI therefore reports **two geometry families, one retained variant, target
three** for this case. Native call counts, validated drafts, rejections, omitted
similar lines, returned count and distance eligibility remain public diagnostics.

The limitation here is bounded candidate generation and diversity, after a valid
three-option proposal; it is not a model timeout or proof that the graph cannot
support a third suitable loop. Strict arrival rejects some attempted place
groups. No third family or visit is invented. Earlier exploratory searches found
a 54.8% woodland line with one checked visit, but did not establish three forest
loops with several historical visits. The final set's best woodland share is
42.0%; loop-shape preference also explains why a less wooded round is retained.
The UI explicitly reports the unsatisfied predominantly-woodland preference and
shows urban/unknown shares. Surface, access and exact repetition remain unknown.

Repeated host runs preserve candidate identities, selected round, native geometry,
authoritative distances and GPX. Independent Python validation checks canonical
requests/results and submitted candidates against actual native receipts, Nature
distance partitions, original component hashes and GPX vertex equality. Each
export has one track/segment, checked waypoints only and no extensions.
Private evidence and exact coordinates/GPX remain outside Git.

The latest **real-account Fairphone** test is separate from that fixture. It
retains 35.987 / 33.735 / 38.195 km native lines, all within the actual request's
35 km ±3.5 km tolerance, with 0 / 1 / 4 checked visits. All three pass the existing
geometry-family proxies, although the first and third still share substantial
linework. Exactly 16 native calls and two cache hits were observed. The retained
woodland shares are only 20.8% / 15.8% / 19.8%, with 30.8–48.4% unknown landcover.
The revised round reaches 34.3% woodland but loses the loop-shape comparison;
valid researched stories survive that rejection. Thus count interpretation,
inference, native validation and three distance-feasible families now pass.
Bounded candidate search and the portfolio quality tradeoff still limit forest
adherence; graph infeasibility has not been established. The UI states the
woodland shortfall explicitly and does not count unknown landcover as forest.

## Anecdotes and claim evidence

Reached places lead the story list. Each card retains proposal identity, local
name/identity, checked outcome, omission reason, short narrative, safe source
links and the historical-verification limitation. Coverage counts describe
source-linked AI anecdotes rather than verified history. Stories-only research
cannot modify routing points, candidates, analysis, ordering or GPX. Recovery
preserves the enriched result exactly and accepts earlier snapshots without the
new optional timing fields.

The previous physical run had four reached places and zero source-linked reached
stories. The c84048d physical run also had zero observed-source anecdotes on its
three reached places. The host fixtures are not completed model research and
remain labeled accordingly. The follow-up requests hosted-search source metadata
as well as response citations and preserves their distinct provenance; neither
independently verifies a claim. The latest ea746cf physical run improves selected
reached-place coverage to three source-linked anecdotes out of four visits.
Independent retrieval supports the narrow Auberderie and Arches claims described
in the physical report. The Champ-de-Mars catalogue claim remains unconfirmed
after retrieval failures, and the hunting table has no anecdote/source. Saved AI
stories retain their unverified labels; the review does not mutate the snapshot.

Independent source retrieval for two of the physically visited names is feasible:
the Ministry of Culture's [Mérimée notice IA00050244](https://pop.culture.gouv.fr/notice/merimee/IA00050244),
historical description, identifies both Batterie de Marly and Batterie de
l'Auberderie in the Marly defensive ensemble. The
[ONF Marly management document](https://www.onf.fr/%2B%2Bamgt%2B%2BA016617C/%2B%2Bzfiles%2B%2B4f66da90#page=41),
printed p. 34 (PDF p. 41), names those batteries in its discussion of artillery
fortifications built around Paris after 1870. This supports that narrow contextual
claim; it does not verify every sentence of the earlier AI narratives, exact
construction dates of each battery or present-day access. The same ONF document
lists hunting tables ambiguously; it does not independently establish the exact
Carrefour du Chêne table identity. A generic “Viewpoint” is also insufficiently
identified for a historical claim. Those gaps remain explicit. No historic account
was hardcoded into routing or retroactively marked verified in a saved result.

## Usability and security

French devices receive French core adventure/speech controls, progress and model
failure messages, including the native Android-provider disclosure. The explicitly
chosen speech-provider enum is remembered through the existing optional PWA store;
no audio, transcript or consent receipt is stored. Restoring the preference never
starts recognition or inference, and native consent still applies to each use.
The editable transcript, append behavior and foreground limits remain.

The [focused authentication/security review](ai-adventure-security-review.md)
covers OAuth, listener, identity/scope validation, protected storage, refresh,
switching/sign-out, bridge, cancellation, fixed endpoints, disclosure, untrusted
model/research data, permissions and production build behavior. No new blocking
credential/bridge finding was identified; live lifecycle evidence remains
distinct from source review and synthetic tests.

## Integration status

Python uses 3.13, uv, Ruff and strict mypy. At the installed ea746cf source,
`make check` passes (303 typed files; 1,612 tests; 16 integration tests deselected;
nine existing NumPy warnings). All 61 browser harnesses, 18 self-contained browser
drivers and Android JVM tests (Debug 288, Release 283, staging 283) pass, as do all
three lints/assemblies. All 153 declared web assets match each APK. The staging
certificate, CA/catalog, unchanged native library and 16 KiB alignment are audited;
no private regional database is packaged. All four required GitHub workflows pass.
The final documentation-only follow-up does not change the tested APK source.
Six older real-service visual drivers require
their separate six-profile server/map fixture and are not represented as passing
by the component harnesses. No CI requirement is removed.

The user separately authorized both staging installations and each two-call live
test. The latest installed artifact is ea746cf, SHA-256
`bc17d1d8ef48fbae6c885361d71557bf2c3fe72247605de304bbb27b50d97796`.
Exact native GPX and restart recovery pass. The original 23.172 km route, editor
text and explicit Android speech-provider choice are restored, with no recording
started. All four authorized calls across the two tests are used; there is no
pending installation approval. A different APK or further real calls need new
separate approval. No app-data clearing or production/Play/hosting change occurred.
At this milestone PR #110 remained draft and unmerged because the forest/history
quality target was not satisfied. See the subsequent route-quality report for
the current measured acceptance and merge status.
