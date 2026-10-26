# Fairphone stabilization acceptance — 26 October 2026

This is actual connected-account and native Android execution, not a model
fixture. Source `c84048d`; audited staging APK SHA-256
`7958ee49b91e7e7249fa39d21cdb0b8e1e723594958c30b2c15daaa99bb0d811`.
The user separately authorized installation with retained data and at most two
real model calls. The previous installed APK and exact route were backed up first.
No production, Play, hosting or regional data was changed.

The exact requested French sentence was entered as editable **typed text** through
the normal adventure dialog. This is not a fresh speech-quality measurement.
The previously verified Android speech-provider behavior remains separate evidence.
The available connected-account model selected in the UI was `gpt-6.1-sol`.

## Actual timing and usage

| Measurement | Previous physical acceptance | c84048d acceptance |
| --- | ---: | ---: |
| Initial model response | 59.084 s | 104.462 s |
| Second model response | 41.543 s | 41.969 s |
| Model calls | 2 | 2 |
| Input tokens | 19,276 | 40,630 |
| Output tokens | 3,442 | 3,890 |
| Total tokens | 22,718 | 44,520 |
| End-to-end | approximately 106 s | 152.017 s |

This does **not** demonstrate a latency or usage improvement. Different model
research and output make this a real product observation, not a controlled speed
comparison. Request bodies were 14,336 and 19,171 bytes. Initial headers arrived
at 2.000 s, first semantic event at 2.054 s and first text at 48.168 s. The observed
research-event span was 25.368 s; stream duration was 102.461 s. Second headers
arrived at 1.589 s and first text at 11.584 s; no complete research span was
observable for that call. These do not expose provider-internal reasoning time.

Local measurements: context 512 ms; grounding 16.8 ms; native routing 2,879.4 ms;
Nature 419.5 ms; publication 118.4 ms; elevation 1,000.1 ms. Routing plus Nature
and publication took 3,591.5 ms. Inclusive phase measurements are not additive.

## Three-option diagnosis and preferences

The first proposal correctly interpreted three alternatives, proposed seven
places and locally grounded six. Eight native calls yielded three retained lines,
two geometry families and one comparison variant; two lines met tolerance.
The final optional strategy proposed four grounded places. Its eight native calls
yielded three geometry families within tolerance. All 16 calls were real and
accounted by the shared cached context; no extra call allowance was added.

The revised portfolio lost the measured route-quality comparison: its loop-shape
penalties were approximately 3.260–3.776, compared with the first round's best
1.293, and its woodland shares were only 23.7–27.1%. It was not promoted merely
to display a count of three. The first round remained authoritative.

| Retained first-round line | Distance | Within tolerance | Reached | Woodland | Urban | D+ |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| Comparison | 35.268 km | yes | 0 | 34.3% | 42.1% | 390.825 m |
| Checked-place option | 35.196 km | yes | 3 | 18.0% | 52.3% | 337.0975 m |
| Other retained line | 37.533 km | no | 3 | 36.5% | 38.5% | 398.385 m |

Thus the explicit-three inference and proposal are established, and the graph
can produce three distinct distance-feasible lines in the revised round. The
quality-selection gate rejects that weaker portfolio. **Three good forest/history
alternatives are still not established.** The UI reports distinct families and
comparison variants separately, plus the unsatisfied forest preference. It does
not infer surface suitability, current access or exact repetition.

## Stories and provenance

The chosen checked-place option reached Table Royale du Carrefour du Chêne,
Batterie des Réservoirs and Batterie de Marly through validated approaches.
Those three had null anecdotes and no observed matching source citation.
The source URLs proposed for other places remained unverified; a plausible URL
was not promoted into historical verification. Source coverage for reached
stories was zero. This remains a product limitation, not a sourcing success.

The follow-up therefore defers historical research until local visits are known,
supplies reached OSM identities/names to the final call and retains identity-bound
story improvements even when the revised route strategy loses. It also requests
the documented hosted-search source list and labels a returned research source
separately from an inline response citation. Neither establishes claim support or
independent historical accuracy. Deterministic tests cover these boundaries;
new live behavior requires another separately authorized artifact/test.

## Real export, map interaction and recovery

The normal candidate button selected the 35.196 km three-place route. Story-map
focusing retained the exact candidate, source and output hashes and added zero
model or route calls; attribution remained visible.

Normal Export opened Android's document picker. The file saved under a new
Downloads filename equals the canonical selected-candidate GPX byte for byte:
SHA-256 `11ea62bbfb03b47c74f8b0e0382e1f44223c3c0bffd63ee69fc983129f0ee0ed`,
63,100 bytes, 1,445 matching track points, three validated waypoints, one track
and one segment, no GPX route or extensions.

A complete staging force-stop/restart offered explicit Reopen with no fabricated
selected route at startup. Reopen restored exact hashes of the complete output,
stories, measurements, selected candidate, source request and canonical GPX.
The original 23.172 km candidate, portfolio, source and editor text were restored
without routing. Its GPX SHA-256 remains
`52b5d326937e532bb4e4a3f66ce625774674d85b3c15ed97320332cfcb5ca6f0`.
The protected connected account survived installation and restart.

Private exact routes, backups and measured receipts stay outside Git. Public
reports contain sanitized timings, counts and explicit limits rather than raw
authenticated traffic, provider output, account identities or private coordinates.
All four GitHub checks passed on `c84048d`; that success is separate from the
unsatisfactory route/story/latency outcome. PR #110 remains draft and unmerged.
