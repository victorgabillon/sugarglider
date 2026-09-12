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

## One-time user action

Use the existing app’s upload key. If it is unavailable, follow the existing
Play Console upload-key recovery/reset procedure before considering a replacement.
For a publisher-authorized new key, the publisher
must explicitly choose to create and safeguard one. Run the following only after
that decision, in a private directory outside every repository; `keytool` prompts
for passwords and identity instead of putting them in shell arguments:

```sh
umask 077
mkdir -p /approved/private/android-signing
keytool -genkeypair -v -keystore /approved/private/android-signing/upload.jks -alias upload -keyalg RSA -keysize 3072 -validity 10000
```

The path is an operator-supplied placeholder. Do not overwrite an existing key.
Keep encrypted recovery copies and the certificate fingerprint under the
publisher's control. The upload key and Play App Signing key have different roles;
review the current [Android signing guide](https://developer.android.com/studio/publish/app-signing)
and Play Console instructions before enrollment. Do not send passwords or private
key material through a chat, issue or pull request.

Create a permission-`0600` Java properties file outside the repository using a
local editor or secret manager. It must contain exactly these four entries:

```properties
storeFile=/approved/private/android-signing/upload.jks
storePassword=REPLACE_LOCALLY
keyAlias=upload
keyPassword=REPLACE_LOCALLY
```

Use standard Java properties escaping for special characters. Both the properties
file and keystore must resolve outside the checkout; relative paths, missing or
partial configuration fail explicitly. No signing value is printed by the build
configuration. The ignore rules are a last defense, not permission to keep secrets
in the checkout. Do not use build scans, verbose build logging or configuration
cache when handling signing credentials.

## Public privacy policy

Set `SUGARGLIDER_ANDROID_PRIVACY_POLICY_URL` to the publisher-approved active HTTPS
policy page when building the final upload. It must have no credentials, query
or fragment. It is public configuration, not a signing secret. The native Privacy
dialog and location-sharing disclosure expose the link without discarding the
current planner page. Without this variable, local privacy details remain
available, but the required public-link gate is unfinished.

## Signed release build

```sh
export SUGARGLIDER_ANDROID_SIGNING_PROPERTIES=/approved/private/android-signing/upload-signing.properties
cd android
./gradlew --no-daemon --no-configuration-cache bundleRelease
jarsigner -verify -verbose -certs app/build/outputs/bundle/release/app-release.aab
sha256sum app/build/outputs/bundle/release/app-release.aab
stat -c '%s bytes' app/build/outputs/bundle/release/app-release.aab
unset SUGARGLIDER_ANDROID_SIGNING_PROPERTIES
```

Verify the signer's certificate fingerprint against the publisher's expected
upload certificate. Bundle generation/signature verification alone does not prove
Play eligibility: validate with a pinned official bundletool, inspect generated
release APKs and run the full Fairphone acceptance matrix. The final ledger must
identify the exact final artifact, signing status and all pending human submission
actions. Keep artifacts outside Git.
