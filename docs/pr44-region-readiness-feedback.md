# PR44 — completed regional checks and native screen contrast

Visible Fairphone acceptance of the patched MapLibre build found that the region
panel kept its initial “Checking regional data…” text after discovering no
installed region. Selecting and verifying an installed region could similarly
leave its progress message behind. The routing gate itself correctly stayed
unavailable without a region; this change makes the status text truthful too.

The region screen now reports completed no-region/selection failures, active
verification and successful readiness explicitly. A failed optional catalog
refresh remains visible while an already installed region stays usable. A later
successful explicit check clears that warning. Operation failure and cancellation
feedback survives the subsequent check of the retained valid region, so the
readiness fix cannot turn a failed update into a success message.

The Android configuration and renderer-recovery pages use dark status-bar icons
on their light background. Opening the green planner/sharing chrome switches
back to light icons. No new permission, tracking action, native authority or
persisted planner state is introduced. The shared shell advances to v42, retaining
the same 103-file Android allowlist and patched local MapLibre modules.

## Validation

`make check` passes 1,055 tests / 16 existing integration tests deselected, Ruff
and strict mypy. The 21 relevant browser harnesses pass 366 cases. The regional
product harness now explicitly checks finished empty discovery, completed
verification/removal, catalog failure/recovery and preservation of failed/cancelled
update feedback. The prior six other UI harnesses retain their 114 passing cases;
this change does not alter those flows.

The preceding patched Fairphone APK also passes a physical keyboard check: the
viewport changes from 372×709 to 372×430 CSS pixels, the focused distance field
remains fully visible at y=332.8–376.8, its value stays 20, and dismissing the
keyboard restores height 709. The keyboard was closed and scroll restored. This
validates the unchanged native inset implementation.

The full Android command (`testDebugUnitTest lintDebug testReleaseUnitTest
lintRelease assembleDebug assembleRelease bundleRelease`) passes in 4 min 42 s:
196 tests per variant, zero failures/errors/skips, and the existing two debug / one
release lint warnings. All 103 packaged shared assets and the ARM64 native library
match source in both artifacts. Official bundletool 1.18.3 validates the unsigned
release AAB.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Debug APK | 151,938,674 | `ad83ccb0a4c39e6031acf8606fd451e76037f88c02eedce77af68519ccafe8fa` |
| Unsigned release AAB | 47,496,095 | `88c9cb2aecb96553bbc2387b53b8c10281388021adb9df7dedb1d60328d6b691` |

The AAB is retained outside Git at
`/tmp/sugarglider-pr44-feedback-unsigned.aab`. `adb install -r` upgrades only the
debug package in place. On the visible, unlocked Fairphone 6 / API 36, completed
empty discovery reports `regional_required` and “Download a region to plan and
view maps offline.” Deliberately crashing the empty WebView renderer leaves native
PID 5760 alive and displays the recovery page with legible dark system-bar icons.
Explicit Reopen returns to the bundled HTTPS planner with Generate disabled.
No active route, GPX operation or participant sharing existed during this test.
The original automatic rotation is restored and no ADB forward remains.

No region was downloaded, no routing or location service started, and no
production-region acceptance is inferred. Public download hosting, final
region/planning tests, public privacy details and publisher actions remain open
in the V1 ledger. The user has deferred these external decisions until the end of
this first goal pass and has explicitly prohibited Play publication.
