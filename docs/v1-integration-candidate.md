# Local V1 code 2 integration candidate

**READY FOR WORK PUBLICATION** describes the completed preparation pass. It does
not close the original PR gates, physical consumer-region acceptance or release
signing, and does not authorize publication or merge to main.

## Source and preserved history

Local branch: `integration/v1-code2`.
Worktree: `/home/pompote/oldata/victor/sugarglider-v1-code2`.
Base: current `main` / `origin/main`,
`d129c22a808c0031c0bb09174ecbc5c22dfbda8d`.

The fourteen draft heads below were merged sequentially with `--no-ff`, starting
with production-region #41 and continuing through #43–#55. Every merge completed
without conflicts. The complete application integration is
`680a52a222710ccec8376b150e0a59439adb7efa`. Publication sources, privacy-copy guard,
acceptance preflight and request fixtures were initially committed in
`99ed28fd10781f5af880280bdea26a0075333b2c`; the final handoff commit additionally
prevents the preflight from reusing response cookies. Its exact final commit is
recorded outside Git in `work-publication-code2/final-preparation.json` to avoid a
self-referential commit hash.

| PR | Source branch | Source head | Local integration merge |
| --- | --- | --- | --- |
| [#41](https://github.com/victorgabillon/sugarglider/pull/41) | `feat/pr42-production-region` | `86cf7e0193b7f4a106ef009734eb688debbb4d96` | `ae7858a39680a8a578604756b05cbb90037623e1` |
| [#43](https://github.com/victorgabillon/sugarglider/pull/43) | `feat/pr41-local-canonical-export` | `dad310cfcd0dd23720963388eb99e2268b073dde` | `270791098d521618e26486fc119221a889a0f0f3` |
| [#44](https://github.com/victorgabillon/sugarglider/pull/44) | `feat/pr41-normal-local-planner` | `af37a1f659f0b49fe0302b2dfb594fbe2cebc5cf` | `ef42c7d7c655cbe2a0c1958adaca964436789928` |
| [#45](https://github.com/victorgabillon/sugarglider/pull/45) | `feat/pr41-bundled-android-shell` | `5f43bce100206e868a9222a8ae274195b736c0c3` | `554ce9d6099212bf2efc4554af79d244967b4da3` |
| [#46](https://github.com/victorgabillon/sugarglider/pull/46) | `feat/pr41-production-native-routing` | `b8ebe3a4f335f1bbcfd8c95b4ad65ff2c2007158` | `3581e3d8f3fc0700cf7f0a3a14d6211e5ed6bfe2` |
| [#47](https://github.com/victorgabillon/sugarglider/pull/47) | `feat/pr42-region-integrity` | `4ac910cd1dba9b6596946ac54fb43f75583c07e6` | `d66f66e8a9d9328373c5617245d7778bfb3acb0d` |
| [#48](https://github.com/victorgabillon/sugarglider/pull/48) | `feat/pr42-versioned-region-installation` | `0f7984508cdce1946985e7f1e3bf1f1580b3d8ce` | `35de4bcba48f4e96b174e9405cf4f60a3a096ce9` |
| [#49](https://github.com/victorgabillon/sugarglider/pull/49) | `feat/pr42-native-regional-transfers` | `e7dc6804171e44865c2175ecf94cc446037fe202` | `36f1f066c03e343d91787594a88174f7a277a677` |
| [#50](https://github.com/victorgabillon/sugarglider/pull/50) | `feat/pr42-regional-runtime-bridge` | `1ac0a3ccaeea0e276b8502a522169f092ed5d903` | `ef2aadfe75b8a370b8a074a5ed838a657542c33a` |
| [#51](https://github.com/victorgabillon/sugarglider/pull/51) | `feat/pr42-region-product-ui` | `b568418cdd7af06e0f474199943043824946b6b2` | `d9a3803b673b61d505d0db377be01842146f14af` |
| [#52](https://github.com/victorgabillon/sugarglider/pull/52) | `feat/pr42-static-distribution` | `9ed8dbe3cf757638af846882e7e0046443eda95c` | `c9ae3b45bf4ba2f8cdc7b2a9e801a67b47bfe4f8` |
| [#53](https://github.com/victorgabillon/sugarglider/pull/53) | `feat/pr44-production-release-hardening` | `e58acdd0d8d03e2570cf5f6ecf64562f7e0f0c4f` | `57f5131abaca55d6bf6b9a368c0d03e311e11a98` |
| [#54](https://github.com/victorgabillon/sugarglider/pull/54) | `fix/pr44-maplibre-attribution-security` | `de76b9543f419e2964fb354d7149303ea02cd0a3` | `0b6851a0c5dac4c03c75320922847a9ae583edba` |
| [#55](https://github.com/victorgabillon/sugarglider/pull/55) | `fix/pr44-region-readiness-feedback` | `ce4d8b70a16d7dda54203298033b4f0314ed5a61` | `680a52a222710ccec8376b150e0a59439adb7efa` |

Obsolete independent PR #42 / `feat/pr44-release-audit`, head
`2ab30b837c59eb6597a4413c063c6aa0f9f467d1`, was excluded. Its head is not an
ancestor of this integration (`git merge-base --is-ancestor` exits 1). No content
was copied from that worktree. Original branches, draft reviews and milestone
history remain intact; a local merge does not mark their acceptance gates passed.

The application contains the production local planner and Valhalla router,
regional staged installation/update/removal, Yvelines catalog support and static
transport contract, signing/privacy/lifecycle hardening, MapLibre security patch
and completed regional-readiness feedback. Android and shared runtime assets are
byte-identical to #55 head `ce4d8b70a16d7dda54203298033b4f0314ed5a61`.
The independent #41 addition supplies production region build/specification code;
no old #42 application implementation is imported.

## Validation and artifact identity

- `make check`: 1,099 tests pass, 16 existing integration tests deselected; Ruff
  format/lint and strict mypy pass. New publication/preflight tests are offline
  and use mock HTTP transport; they do not execute final device acceptance.
- All 27 relevant browser harnesses pass 480 cases. Canonical cross-validation
  covers 51 PlanResults, 30 submitted native fixtures, 16 diagnostics and 60 GPX
  comparisons. One expected aborted fixture request emitted a local server
  BrokenPipe message; the full runner exited successfully.
- Android debug and release: 196 unit tests each, no failures/errors/skips; both
  lints pass with two debug / one release existing warnings and zero errors.
- Debug assembly, release assembly and `bundleRelease` pass; one bounded Gradle
  invocation completed 125 tasks in 6 min 17 s. No signing configuration was used.
- Official pinned bundletool 1.18.3 validates the unsigned release bundle.
- All 103 declared shared assets match source in both APK and AAB; shell cache
  remains v42. The sole ARM64 library matches in both packages: SHA-256
  `e60d66dba922a17c53397e4a00ba4380a9ec87f8f203d3761fefe86bef9b2bbb`.
- `git diff --check` passes. The final preflight-cookie and documentation changes
  do not alter Android, shell assets or the validated application artifacts.

Application source for these build outputs is
`680a52a222710ccec8376b150e0a59439adb7efa`.

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| Debug APK | 151693222 | `8e46ad192b397ae89bf7db0ef94ce0bb0d70930ef55ff97ae4d5f3c260e12ece` |
| Unsigned release AAB | 47496491 | `2539fe371de8a51261f98cc713c7b4b7857f1630b7317b574b0a0e95a4114113` |

Build paths under the integration worktree:
`android/app/build/outputs/apk/debug/app-debug.apk` and
`android/app/build/outputs/bundle/release/app-release.aab`.
Exact preserved copies are under
`/home/pompote/oldata/victor/sugarglider-v1-artifacts/work-publication-code2/integration-artifacts/`.
The companion `integration-artifacts.json` records all sizes/hashes and variant
results. `integration-graph.json` records the full audited dependency graph.
Validation logs and runner are preserved in that artifact root's `validation/`.

The exact Android validation invocation, from the integration `android/` directory:

```sh
env JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 ANDROID_HOME=/home/pompote/Android/Sdk ANDROID_SDK_ROOT=/home/pompote/Android/Sdk systemd-run --user --scope -p MemoryMax=3G -p CPUQuota=200% ./gradlew --offline --no-daemon --no-configuration-cache --max-workers=1 -Pkotlin.compiler.execution.strategy=in-process -Dorg.gradle.jvmargs=-Xmx1400m testDebugUnitTest lintDebug testReleaseUnitTest lintRelease assembleDebug assembleRelease bundleRelease
```

## Preserved state and open gates

The integration branch remains local and unpushed. Main and the original checkout
remain unchanged. The protected original untracked `Continue,` and `native` entries
were not read, changed, staged, moved or deleted. The original stash remains
`6abe302207f4336b04e3a050966c263c218393a1`. This task performed no phone operations,
radio/hotspot changes, data clearing, real signing, public hosting, Play upload or
merge/push to main.

The embedded catalog intentionally still has `manifest_url: null`; download
unavailability remains visible. The public privacy build setting is unset. Work
must publish/review and return the exact public observations in the
[copy-paste handoff](work-publication-handoff.md). Codex then verifies those bytes,
embeds the returned catalog/policy, advances the shell cache and rebuilds/rechecks.
No newly hosted URL is asserted live by this preparation.

The [final Fairphone driver/checklist](v1-final-device-acceptance.md) is prepared
and **not run**. Consumer-region install/planning/restart/storage/timing and final
release-specific acceptance remain open. The first catalog contains one version;
physical update measurements remain pending a genuinely different prepared second
version. Existing automated update tests are separate evidence.

[Real signing](pr44-signing-and-bundle.md) awaits the existing external upload-key
backup/configuration path, alias, locally provided passwords and expected public
certificate fingerprint. Work must confirm the next version code remains unused.
The validated unsigned AAB is not a signed release and was not installed on the
Fairphone. Its existing Play-installed code 1 / name 0.1.0 remains untouched.
