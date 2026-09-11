# Android release signing and bundle preparation

This prepares an external upload-key workflow. It does not make the current
release a V1 candidate: release local planning, regional installation and the
mandatory phone acceptance still need PR40–42. No permanent key has been created.

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

Use the publisher's existing upload key if one exists. Otherwise, the publisher
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
