import java.net.URI
import java.nio.file.Files
import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val sharedWebDirectory = rootProject.file("../src/sugarglider/web/static")
val shellAssetList = rootProject.file("shell-assets.txt")
val shellAssetPaths = shellAssetList.readLines().filter { it.isNotBlank() && !it.startsWith('#') }
require(shellAssetPaths.isNotEmpty() && shellAssetPaths.distinct().size == shellAssetPaths.size)
require(shellAssetPaths.all { path ->
    !path.startsWith('/') && '\\' !in path && path.split('/').none { it in setOf("", ".", "..") }
})
val bundledShellDirectory = layout.buildDirectory.dir("generated/bundled-shell")
val bundleSharedWebShell by tasks.registering(Sync::class) {
    inputs.file(shellAssetList)
    from(sharedWebDirectory) { include(shellAssetPaths); into("web") }
    from(shellAssetList)
    into(bundledShellDirectory)
    doFirst {
        require(shellAssetPaths.all { path ->
            val source = sharedWebDirectory.resolve(path)
            source.isFile && !Files.isSymbolicLink(source.toPath())
        }) { "The declared shared Android shell is incomplete." }
    }
}

// Release secrets are optional for unsigned validation and must live outside Git.
val externalSigningPath = providers.environmentVariable("SUGARGLIDER_ANDROID_SIGNING_PROPERTIES")
    .orNull
val externalSigning = externalSigningPath?.let { path ->
    val repository = rootProject.projectDir.parentFile.canonicalFile.toPath()
    val propertiesFile = File(path)
    require(propertiesFile.isAbsolute && propertiesFile.isFile) {
        "Android signing configuration must be an existing absolute external file"
    }
    require(!propertiesFile.canonicalFile.toPath().startsWith(repository)) {
        "Android signing configuration must be outside the repository"
    }
    val properties = Properties()
    try {
        propertiesFile.inputStream().use(properties::load)
    } catch (_: Exception) {
        throw GradleException("Unable to read external Android signing configuration")
    }
    val required = setOf("storeFile", "storePassword", "keyAlias", "keyPassword")
    require(properties.stringPropertyNames() == required &&
        required.all { !properties.getProperty(it).isNullOrBlank() }) {
        "Android signing configuration requires exactly storeFile, storePassword, keyAlias and keyPassword"
    }
    val keyStore = File(properties.getProperty("storeFile"))
    require(keyStore.isAbsolute && keyStore.isFile &&
        !keyStore.canonicalFile.toPath().startsWith(repository)) {
        "Android upload keystore must be an existing absolute file outside the repository"
    }
    properties
}

// Publisher-approved public URL; independent from the external upload-key secrets.
val publicPrivacyPolicy = providers.environmentVariable("SUGARGLIDER_ANDROID_PRIVACY_POLICY_URL")
    .orElse("https://victorgabillon.github.io/sugarglider-regions/privacy/").get()
if (publicPrivacyPolicy.isNotEmpty()) {
    val uri = runCatching { URI(publicPrivacyPolicy) }.getOrNull()
    require(publicPrivacyPolicy.length <= 2_048 && uri != null && uri.scheme == "https" &&
        uri.host != null && uri.userInfo == null && uri.query == null && uri.fragment == null) {
        "Privacy policy URL must be a public HTTPS URL without credentials, query or fragment"
    }
}

android {
    namespace = "io.github.victorgabillon.sugarglider"
    compileSdk = 36
    buildToolsVersion = "36.0.0"

    defaultConfig {
        applicationId = "io.github.victorgabillon.sugarglider"
        minSdk = 26
        targetSdk = 36
        versionCode = 4
        versionName = "1.0.2"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("boolean", "ALLOW_HTTP", "false")
        buildConfigField("String", "PRIVACY_POLICY_URL", "\"$publicPrivacyPolicy\"")
        ndk.abiFilters += "arm64-v8a"
    }

    signingConfigs {
        externalSigning?.let { properties ->
            create("externalUpload") {
                storeFile = File(properties.getProperty("storeFile"))
                storePassword = properties.getProperty("storePassword")
                keyAlias = properties.getProperty("keyAlias")
                keyPassword = properties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            buildConfigField("boolean", "ALLOW_HTTP", "true")
        }
        release {
            signingConfig = externalSigning?.let { signingConfigs.getByName("externalUpload") }
            isDebuggable = false
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }

    sourceSets.getByName("main").assets.srcDir(bundledShellDirectory)
}

tasks.named("preBuild").configure { dependsOn(bundleSharedWebShell) }

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
        freeCompilerArgs.add("-Xjsr305=strict")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.webkit:webkit:1.15.0")

    implementation("io.github.rallista:valhalla-mobile:0.5.1")
    implementation("io.github.rallista:valhalla-models:0.1.1")
    implementation("io.github.rallista:valhalla-models-config:0.1.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.moshi:moshi-kotlin:1.15.1")
    testImplementation("org.json:json:20250517")
}
