# Temporary Android audit installations

The historical audit suffixes accumulated because physical audits installed each
new package under a different application ID. Each remained a separate Android
application, with independent regional data and browser storage. Sharing a launcher
label did not establish that its data was disposable.

Ordinary GUI testing uses the canonical `.v2staging` application and a separately
authorized, data-preserving replacement. Never uninstall that application to update
it. Keep its current APK, complete planner/adventure snapshots, exact selected GPX,
account-status evidence and regional integrity receipts before replacement.

For an isolated audit, use a fresh `.v2audit<run-id>` suffix. The staging manifest
already removes `android.intent.category.LAUNCHER` for these suffixes while keeping
MainActivity explicitly launchable for instrumentation. This avoids adding drawer
icons without changing ordinary staging or instrumentation support.

A physical audit session must own its cleanup:

1. Choose one exact `.v2audit[a-z0-9]{1,16}` package and its exact `.test` helper.
   Verify that both are absent before installation. If either exists, choose a new
   run ID; never treat a pre-existing installation as temporary.
2. Verify both APK package identities, instrumentation target and signing
   certificates. Reject production and `.v2staging` unconditionally.
3. Record the run's APK hashes, versions, serial and exact newly created packages.
4. Run the required audit through explicit Activity/instrumentation entry points.
5. In the runner's `finally`/exit cleanup, verify that each package still has the
   run's identity and is not being used by another worker, retain its useful audit
   evidence, and uninstall only the exact packages created by that session.
6. Record the cleanup outcome. An interrupted or uncertain cleanup becomes an
   explicit follow-up item, never permission to remove older copies by prefix.

Existing installations require their own data review and applicable authorization.
Do not batch-uninstall by a wildcard, display label, substring or package prefix.
Non-launcher helpers do not contribute drawer clutter and may still be needed for
instrumentation.
