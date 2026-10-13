# PR86 — Valhalla Mobile 0.6.4 / Valhalla 3.9.1 upgrade

**Status: upgrade candidate, gated by physical compatibility acceptance.**
This is a *native engine* update, not just the Kotlin model/API wrapper. The
previously installed 3.6.3 graph archives MUST remain usable or this PR
cannot be promoted to a release. No signed AAB, public region or Play track is
modified here.

## Source identity and scope

- Android pin: `io.github.rallista:valhalla-mobile:0.6.4`.
- Matching upstream model artifacts:
  `valhalla-models:0.6.0` and `valhalla-models-config:0.6.0`.
- [Valhalla Mobile 0.6.4 release](https://github.com/Rallista/valhalla-mobile/releases/tag/0.6.4)
  upgrades native Valhalla to **3.9.1** (the README badge is not authoritative
  for the final patch version).
- Native actions newly exposed since 0.5.1 include `trace_route`,
  `trace_attributes`, `height` and `sources_to_targets`. The `height`
  action reports null with no configured elevation tiles. **This PR does not
  enable or advertise elevation data, D+/D−, map matching or matrix planning.**
- Old routing pack schema v2, `engine_version: 3.6.3`, and the published
  3.6.3 archive descriptors remain **unchanged**. The application reports its
  actual new runtime version separately as
  `0.6.4/valhalla-3.9.1`. Compatibility of the old graph bytes is a
  *physical acceptance gate*, not a claim proved by successful Kotlin tests.
- All existing production Android preferences and signed code 8 / 1.2.0
  remain unchanged; future release version/code increments are separate.

## Native actor lifetime

Unlike wrapper 0.5.1, which built an actor inside each JNI route call, 0.6.4
creates one persistent native actor in its Kotlin `Valhalla` constructor
and requires explicit `close()`. The code now:

1. Keeps at most one active actor in `SingleCurrentRoutingPackActor`.
2. Reuses the native actor only for the exact validated pack identity.
3. Closes the previous actor *before* initializing a different region/build,
   bounding native cache usage; failed initialization leaves no stale actor.
4. Closes the actor once when the owning `MainActivity` is destroyed,
   scheduling the close **after** its serialized route worker drains.
5. Updates runtime measurement semantics: cold initialization now includes
   JNI actor construction; warm route timings no longer do.

Unit tests cover same-region reuse, A→A→B→B→A switching, disposal order,
failed initialization and idempotent close. This is not yet proof of
native teardown timing on a physical phone.

## No silent elevation/routing changes

- `localValhallaConfiguration()` continues selecting only the validated
  archive, with empty auxiliary directories, `AdditionalData(elevation = "")`,
  no remote tile URL, and no HTTP server or hosted fallback.
- Route requests remain bounded, typed, one explicit public profile, same
  points and `polyline6` output, same canonical validation/GPX contract.
- Existing 3.6.3 regional build and static publication contracts are left
  alone; no automatic region migration, rebuild or removal is performed.
- The native reader checks at least graph *major* version; its warning rule
  alone does not prove binary schema/layout compatibility across 3.6→3.9.
  A real routing smoke against the old archive is mandatory.

## Acceptance criteria

**Automated (required for PR readiness):**
- `make check`, Android debug+release unit tests, lint and debug APK build.
- Six typed profile policies and request/response parsing remain valid.
- All lifecycle tests pass, including initialization failure and close.
- Inspect produced APK native ABI, 16 KiB page/ELF alignment, and avoid
  unexpected permission or manifest changes.
- Verify old region manifests remain recognizable (no schema/data changes).

**Fairphone 6 (still required before merge for a runtime-breaking upgrade):**
- Use the separate `io.github.victorgabillon.sugarglider.debug` app.
  Preserve the Play-installed `io.github.victorgabillon.sugarglider` package,
  its data, downloaded region and active code 8.
- Confirm an already-installed region whose routing archive was built with
  Valhalla **3.6.3** is recognized without reinstalling or rebuilding it.
- Generate a normal 2–3-point route in each of the six public profiles and
  a representative Auto Tour. Compare to the 0.5.1 baseline for route
  success, snapped endpoints, geometry, distance and time. Route outputs
  may legitimately differ between native engines; review meaningful changes.
- Run warm repeated routes (same selected pack) and region switches
  A→A→B→B→A if two debug packs exist. Check cold/warm time and process PSS.
- Exercise missing/corrupt/incompatible pack failure, background/foreground,
  app recreation and region update/remove while idle. No JNI/native crashes,
  stale region selection, missing safeguards or undeclared online fallback.
- Ensure offline behavior remains offline with an installed region. Do not
  change hotspot, Wi-Fi or radios unexpectedly; a controlled offline test
  must be explicitly coordinated because the phone may supply tethering.

**Blocked until the physical routing evidence exists:** no approval to merge,
publish a Play AAB, upgrade the production package, or republish any region
merely because GitHub CI is green.

## Next milestone

Once PR86's routing upgrade is physically accepted, PR87 can design a
bounded typed `height` request/response with null heights for missing DEM,
and PR88 can supply explicitly versioned, vetted elevation data. D+/D− and
profile UI remain later and require a documented smoothing/coverage policy.
