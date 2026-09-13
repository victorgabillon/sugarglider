# Android release signing and bundle preparation

This configures an external upload-key workflow for the shared production native
router and bundled regional planner. Consumer-region physical acceptance and
final release gates remain open. The V1 preparation did not create a permanent key.

A subsequently supplied user record says an upload key **was already created and
backed up for the previous 0.1.0 internal release**. Reuse that existing identity;
the unresolved action is
locating its private backup/configuration, not creating another key by default.

The same record identifies the public developer name as **Sugarglider** and reports
an active internal release of code 1 / name 0.1.0 on 2026-08-28, with no production
release. These are supplied historical Play Console facts, not a new live Console
inspection. Read-only Fairphone package inspection now confirms code 1 / name
0.1.0 installed by `com.android.vending`, resolving the record's installation
uncertainty. This does not establish successful launch or current track contents.

The Fairphone already contains a Play-installed release with version code 1 /
name 0.1.0. The proposed V1 update uses code 2 / name 1.0.0. The publisher must
confirm that code 2 is unused across every Play track before upload and use the
existing app’s upload-key/App Signing setup. Do not create a new app identity or
replace the existing phone installation with a disposable signing certificate.

The old `chore/play-internal-testing` branch is absent from current local refs and
remote heads. The current signing implementation is already committed/pushed in
`e58acdd` and uses the external four-field properties file described below;
`android/.kotlin/` is already ignored. The old “commit signing configuration” todo
is therefore superseded for V1. Do not restore an unexamined historical Gradle file.
A bounded filename-only check of Downloads, Documents, `.config` and
`.local/share` found no Sugarglider/upload/Play keystore or signing-properties
candidate. No key/password contents were read; this is not proof that the private
backup is missing elsewhere.

## Unsigned validation

With Python 3.13, `uv`, JDK 17 and Android SDK 36 installed:

```sh
make check
cd android
./gradlew --no-daemon --no-configuration-cache testDebugUnitTest lintDebug testReleaseUnitTest lintRelease bundleRelease
```

With `SUGARGLIDER_ANDROID_SIGNING_PROPERTIES` unset, the release bundle is unsigned.
The build never substitutes the debug key. The generated bundle is ignored at
`android/app/build/outputs/bundle/release/app-release.aab`. Record its size, SHA-256,
merged manifest, delivered APK alignment and runtime acceptance only after the
final production implementation. An unsigned bundle cannot be uploaded as a
signed release.

## Existing-key handoff

The current V1 task authorizes preparation only. Reuse the existing app's upload
key; do not create, rotate, copy or search private key contents. Actual signing
waits for the publisher to supply the existing backup/configuration path. The
earlier key-creation example is removed from this active handoff.

Still needed: the absolute existing keystore path outside every checkout, its
existing alias (not assumed to be `upload`), the absolute external signing-properties
path, and the expected **public upload certificate SHA-256 fingerprint** from the
publisher/Console. Passwords are supplied locally, never in chat, shell arguments,
logs or committed files. Work must separately confirm that version code 2 is
unused across the Play tracks before any later authorized upload.

Create a permission-`0600` Java properties file outside the repository using a
local editor or secret manager. It must contain exactly these four entries:

```properties
storeFile=/absolute/path/to/EXISTING-keystore.jks
storePassword=REPLACE_LOCALLY
keyAlias=EXISTING_ALIAS_FROM_PUBLISHER
keyPassword=REPLACE_LOCALLY
```

Use standard Java properties escaping for special characters. Both the properties
file and keystore must resolve outside the checkout; relative paths, missing or
partial configuration fail explicitly. No signing value is printed by the build
configuration. The ignore rules are a last defense, not permission to keep secrets
in the checkout. Do not use build scans, verbose build logging or configuration
cache when handling signing credentials.

## Public privacy policy

The publisher-approved page is now live at
`https://victorgabillon.github.io/sugarglider-regions/privacy/` and is the Android
build's default. Codex verified its published size/hash; see
[publication acceptance](v1-published-region-acceptance.md).
`SUGARGLIDER_ANDROID_PRIVACY_POLICY_URL` remains a public override for a separately
approved HTTPS policy, with no credentials, query or fragment. It is independent
of signing secrets. The native Privacy dialog and location-sharing disclosure
expose the link without discarding the current planner page. The earlier missing
public-policy-host gate is superseded; final device/link acceptance remains open.

## Signed release build, only after the existing setup is supplied

The paths below are explicit placeholders to replace with the existing external
configuration and verified public policy URL. Only the properties file's path is
passed through the signing environment variable. The four properties are read by
`android/app/build.gradle.kts`; no password environment variable or Gradle command
line password input is required. This command has **not** been run in this pass.

```sh
export SUGARGLIDER_ANDROID_SIGNING_PROPERTIES=/absolute/path/to/existing-signing.properties
export SUGARGLIDER_ANDROID_PRIVACY_POLICY_URL=https://victorgabillon.github.io/sugarglider-regions/privacy/
cd /home/pompote/oldata/victor/sugarglider-v1-code2/android
env JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 ANDROID_HOME=/home/pompote/Android/Sdk ANDROID_SDK_ROOT=/home/pompote/Android/Sdk ./gradlew --offline --no-daemon --no-configuration-cache --max-workers=1 -Pkotlin.compiler.execution.strategy=in-process -Dorg.gradle.jvmargs=-Xmx1400m testReleaseUnitTest lintRelease assembleRelease bundleRelease
unset SUGARGLIDER_ANDROID_SIGNING_PROPERTIES
unset SUGARGLIDER_ANDROID_PRIVACY_POLICY_URL
```

Verify the output without opening a keystore or supplying passwords:

```sh
/usr/lib/jvm/java-17-openjdk-amd64/bin/jarsigner -verify app/build/outputs/bundle/release/app-release.aab
/usr/lib/jvm/java-17-openjdk-amd64/bin/keytool -printcert -jarfile app/build/outputs/bundle/release/app-release.aab
/usr/lib/jvm/java-17-openjdk-amd64/bin/java -jar /home/pompote/oldata/victor/sugarglider-v1-artifacts/work-publication-code2/tools/bundletool-1.18.3.jar validate --bundle=app/build/outputs/bundle/release/app-release.aab
sha256sum app/build/outputs/bundle/release/app-release.aab
stat -c '%s bytes' app/build/outputs/bundle/release/app-release.aab
```

Require an actually verified JAR signature; an unsigned JAR is not a success even
if a tool exits zero. Compare the public SHA-256 signer fingerprint with the
publisher's expected **upload** certificate. Keep only public fingerprints in the
handoff, not certificate subject details. The pinned bundletool SHA-256 is
`a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29`.

For a later delivered APK, inspect its distinct Android signature:

```sh
/home/pompote/Android/Sdk/build-tools/36.0.0/apksigner verify --verbose --print-certs /absolute/path/to/delivered.apk
```

Compare a Play-delivered APK with the expected **Play App Signing** certificate,
which may differ from the upload certificate. Do not sideload an upload-key APK
over the existing Play installation. Bundle/signature checks do not close physical
acceptance or authorize upload. Preserve exact final source/artifact identity and
pending gates in the ledger; keep artifacts outside Git.

The integrated candidate is package `io.github.victorgabillon.sugarglider`,
version code **2**, version name **1.0.0**. Its current validated AAB is unsigned;
see [integration evidence](v1-integration-candidate.md). Work owns any later Play
Console action, and no Play upload is authorized by this handoff.
