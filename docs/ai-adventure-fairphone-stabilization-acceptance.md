# Fairphone stabilization acceptance — 26 October 2026

This is the historical ea746cf physical acceptance. Later host real-graph
improvements and current PR status are documented in the
[woodland route-quality report](ai-adventure-route-quality.md). They do not change
these actual phone measurements or the installed APK.

The latest actual connected-account/native Android run establishes three
distance-feasible geometry families and source-linked anecdotes for three of the
selected route's four reached places. GPX equality and exact restart recovery
pass. **Three good forest/history routes remain unestablished:** retained mapped
woodland is only 15.8–20.8%. At that milestone PR #110 remained draft and unmerged.

Both follow-ups used the real Fairphone 6 and actual native Valhalla, Places,
Nature and elevation, with no fabricated model answer or routing output. The
user separately authorized each retained-data installation and two real calls.

| Follow-up | Source commit | Audited and installed staging APK SHA-256 |
| --- | --- | --- |
| Preceding | c84048d | `7958ee49b91e7e7249fa39d21cdb0b8e1e723594958c30b2c15daaa99bb0d811` |
| Latest | ea746cf | `bc17d1d8ef48fbae6c885361d71557bf2c3fe72247605de304bbb27b50d97796` |

The previous installed APK and exact route were backed up first. No uninstall,
data clearing, production, Play, hosting or regional-data change occurred. The
latest APK remains installed, with the original route/editor restored afterward.
All four authorized model calls across these two follow-ups are used.

## Exact input and timing

The exact acceptance sentence was entered as editable **typed text** through the
normal adventure dialog in both follow-ups:

> Je suis à Marly et je veux courir environ 35 km dans les bois, en passant par plusieurs lieux historiques intéressants. Propose-moi trois parcours différents et raconte-moi des anecdotes sur les lieux réellement visités.

This is not a fresh speech-quality measurement. The original voice acceptance
and its verified Android speech-provider behavior remain separate evidence. The
available connected-account model selected in the UI was `gpt-6.1-sol`; runtime
model discovery/selection remains unchanged. The latest request keeps the checked
Marly Start, no inherited exact stops/End, and uses a `trail_run` loop.

| Measurement | Original voice run, two alternatives | c84048d, exact typed request | ea746cf, same typed request |
| --- | ---: | ---: | ---: |
| Initial model response | 59.084 s | 104.462 s | 60.346 s |
| Second model response | 41.543 s | 41.969 s | 65.008 s |
| Model calls | 2 | 2 | 2 |
| Input tokens | 19,276 | 40,630 | 24,375 |
| Output tokens | 3,442 | 3,890 | 3,731 |
| Total tokens | 22,718 | 44,520 | 28,106 |
| End-to-end | approximately 106 s | 152.017 s | 130.968 s |

Against the preceding exact-request run, observed total time decreases 13.8%,
token use 36.9%, and initial-call time 42.2%. Final research takes longer because
it now targets reached places and returns usable citations. This is one observed
comparison with different generated content, not a controlled performance claim
or general guarantee. It does not beat the original two-alternative run overall.

The latest geography-only first call disables research and has no source URLs;
the final research/revision call observes 17 source URLs. Neither call errors or
hits its unchanged 120-second deadline.

| Latest native observation | Initial | Final research/revision |
| --- | ---: | ---: |
| Request bytes | 14,616 | 20,759 |
| Response headers | 1.365 s | 2.542 s |
| First semantic event | 1.407 s | 2.606 s |
| First text | 10.078 s | 18.373 s |
| Observed research-event span | unavailable | 13.117 s |
| Stream duration | 58.980 s | 62.465 s |
| Input / output tokens | 2,853 / 1,928 | 21,522 / 1,803 |

Latest local measurements: context preparation 485.2 ms; input preparation 0.1 ms;
structured validation 13.6 ms; grounding 15.8 ms; native routing 2,992.0 ms; Nature
431.5 ms; publication 118.3 ms; elevation 889.3 ms; routing/Nature phase 3,731.1 ms;
optional refinement 66,872.4 ms. Some phases are inclusive and not additive.
Research-event span is not provider-internal reasoning/tool time.

## Three-option diagnosis and forest limits

The latest first proposal requests three alternatives, proposes eight places and
locally grounds all eight. Eight evaluated sequences yield eight valid native
drafts, three Nature finalists and three retained geometry families within
tolerance; three similar lines are omitted. The second proposal has four places,
all grounded. Ten evaluated/valid sequences include two cache hits and eight
new native calls, yielding three finalists/families within tolerance; four
similar lines are omitted.

The shared context accounts exactly 16 native backend calls under the unchanged
8+8 budget. Cache lookup 18 = hit 2 + miss 16; entry 16 = successful 16 + failed 0;
backend call 16 = miss 16, with zero pre-backend rejections. No export, story-map
interaction or recovery adds a call.

The first round remains authoritative; valid identity-bound story improvements
from the second call are retained even though its route strategy loses. The
request is 35 km with ±3.5 km balanced tolerance and no hard maximum.

| Retained latest line | Distance | Absolute target error | Reached | Woodland | Urban | Unknown | D+ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No-POI comparison | 35.987 km | 0.987 km | 0 | 20.8% | 26.9% | 48.4% | 412.055 m |
| One-place option | 33.735 km | 1.265 km | 1 | 15.8% | 51.5% | 30.8% | 337.8625 m |
| Selected four-place option | 38.195 km | 3.195 km | 4 | 19.8% | 34.6% | 42.1% | 495.5625 m |

All three are distance-feasible. The actual pairwise native-line proxies are:

| Pair | Sampled line separation | Exact coordinate-segment shares, each direction |
| --- | ---: | ---: |
| Comparison / one-place | 1,684.7 m | 17.7% / 18.9% |
| Comparison / four-place | 615.7 m | 70.0% / 66.0% |
| One-place / four-place | 1,690.9 m | 7.3% / 6.4% |

These pass the existing 600 m sampled-line threshold and 85% mutual-sharing
cutoff. They establish three geometry families under the documented proxies,
not independent corridors, exact edge repetition or three equally good tours.
The comparison and four-place lines still share substantial geometry.

The revised round's 35.268 / 37.452 / 37.095 km lines have 34.3% / 32.2% / 21.1%
woodland and 0 / 4 / 1 reached places. Its best loop-shape penalty is 1.293,
versus the retained round's best 0.970, so it loses the portfolio comparison
before the softer woodland preference. This selection policy and bounded
candidate search limit forest adherence. Model inference, count interpretation,
validation and three distance-feasible families succeed; graph infeasibility is
not established. No route meets 50% mapped woodland, even in the revised round.
The UI explicitly reports the retained portfolio's 20.8% best share and keeps
unknown landcover separate. Asphalt, exact repetition, technical difficulty,
current access and surface suitability remain unknown.

For comparison, c84048d's initial proposal grounded 6/7 places and retained
35.268 / 35.196 / 37.533 km lines, with woodland 34.3% / 18.0% / 36.5% and visits
0 / 3 / 3. Only two met tolerance, and the retained set had two geometry families
plus one variant. Its revised three-family portfolio lost on loop shape and had
23.7–27.1% woodland. The latest run resolves distance-feasible family count,
while the forest/history quality goal remains open.

## Reached stories and independent claim checks

The selected 38.195 km route validates four mapped approaches, each within 9 m.
Three have short source-linked AI anecdotes; one correctly has no story/source.
The one-place option reaches only Table Royale and has no sourced anecdote. The
preceding c84048d selected three-place route had zero source-linked anecdotes.

| Latest selected visit | Local identity | Routed arrival distance | Source and independent evidence |
| --- | --- | ---: | --- |
| Batterie de l'Auberderie | OSM node/10099309670 | 6.06 m | [ONF Marly management document](https://www.onf.fr/%2B%2Bamgt%2B%2BA016617C/%2B%2Bzfiles%2B%2B4f66da90#page=41), printed p. 34 / PDF p. 41, “Les batteries militaires”: independently supports the narrow post-1870 battery context and paved service roads. |
| Batterie du Champ-de-Mars | OSM node/13343009316 | 8.72 m | [SHD catalogue GR 3 V 767](https://www.servicehistorique.sga.defense.gouv.fr/ark/1478719): title/reference retrieved, but deeper retrieval failed. The anecdote's precise catalogue-grouping claim remains independently unconfirmed. |
| Table Royale du Carrefour du Chêne | OSM node/13343044822 | 4.31 m | No anecdote/source; exact historical table identity remains insufficiently established. |
| Batterie des Arches | OSM node/13343026372 | 8.48 m | [Ministry of Culture, Mérimée IA00050229](https://pop.culture.gouv.fr/notice/merimee/IA00050229), construction field and historical description: independently supports 1879 construction, the second Paris defensive belt and first-line classification in 1923. |

All three retained links have `response_citation` provenance. Returned hosted
search metadata and actual response annotations remain separately labeled;
neither independently establishes claim support. The independent checks above
support only the stated narrow claims, not all AI prose or present-day access.
They do not mutate the immutable saved response: application stories retain
AI-generated/unverified labels. No unverified narrative enters the GPX.

Reached cards lead the list; omitted places retain explicit outcomes/reasons.
Historical research receives checked local OSM identities, and its valid story
updates survive a route revision that fails the quality comparison. No third
model call or hidden research loop is added.

## Android export, interaction, recovery and restoration

The normal candidate button selects the 38.195 km four-place line. Story-map
focusing preserves exact output, candidate and source hashes; attribution stays
visible, with zero additional model/native calls.

Normal Export opens Android's document picker. The file saved under a new local
Downloads filename equals the selected canonical GPX byte for byte: SHA-256
`f398bf0c00d5fa1e13bdbbc37055a1b393ca44bb8aa67163cef427fbeebe6a47`,
58,948 bytes, 1,344 matching track points, four validated waypoints, one track and
one segment, no GPX route or extensions. The preceding c84048d Android export
also passed: 63,100 bytes, 1,445 points, three waypoints, SHA-256
`11ea62bbfb03b47c74f8b0e0382e1f44223c3c0bffd63ee69fc983129f0ee0ed`.

A complete staging force-stop/restart offers explicit Reopen, with no selected
route fabricated at startup. Reopen restores exact hashes of the entire output,
stories, measurements, selected candidate, source request and canonical GPX.
The protected account survives installation and restart.

The original 23.172 km candidate, portfolio, source and 653-character editor text
are restored without routing. Its original GPX SHA-256 remains
`52b5d326937e532bb4e4a3f66ce625774674d85b3c15ed97320332cfcb5ca6f0`.
The saved language choice and explicitly preferred Android platform speech
provider are restored. Only the provider enum is remembered; the microphone is
inactive and restoration does not record audio or grant consent. The latest
adventure remains available through explicit Reopen. Temporary device debugging
forwards created for this test are removed.

## Checks and remaining limits

At ea746cf: `make check` passes (Ruff, strict mypy, 1,612 tests), all 61 browser
harnesses and 18 self-contained drivers pass, Android JVM Debug 288 / Release 283
/ staging 283 pass, and all three lints/assemblies pass. All 153 declared assets
match each APK. All four GitHub PR workflows pass. Six older real-service visual
drivers require the unavailable separate six-profile server/map fixture and are
explicitly not counted as passing. The final documentation-only update changes
no installed runtime source.

The [focused authentication review](ai-adventure-security-review.md) finds no new
blocking credential/bridge defect; live refresh, switching and remote sign-out
are not deliberately exercised by these tests. Latency remains approximately two
minutes, the initial result is published atomically after optional refinement,
one reached landmark lacks a story, one cited claim remains independently
unconfirmed, and woodland/history quality is insufficient for routine merge.

Private exact routes, GPX, backups and measured receipts stay outside Git. Public
reports contain sanitized timings, counts, public landmark identities and source
checks rather than raw authenticated traffic, full model output, account
identities or private coordinates.
