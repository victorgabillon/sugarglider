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
// Opt-in, isolated storage for acceptance. Never reuses an installed app's UID.
val stagingSuffix = providers.gradleProperty("sugargliderV2StagingSuffix").orElse(".v2staging").get()
require(stagingSuffix == ".v2staging" || stagingSuffix.matches(Regex("\\.v2audit[a-z0-9]{1,16}")))
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
        versionCode = 8
        versionName = "1.2.0"

        testInstrumentationRunner = if (providers.gradleProperty("sugargliderV2Research").isPresent || providers.gradleProperty("sugargliderV2Staging").isPresent)
            "io.github.victorgabillon.sugarglider.V2RegionInstrumentation"
        else "io.github.victorgabillon.sugarglider.HeightResearchInstrumentation"
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
        create("v2Debug") {
            initWith(getByName("debug"))
            applicationIdSuffix = ".v2debug"
            versionNameSuffix = "-v2-research"
            matchingFallbacks += "debug"
        }
        create("v2Staging") {
            initWith(getByName("debug"))
            applicationIdSuffix = stagingSuffix
            versionNameSuffix = "-v2-staging"
            buildConfigField("boolean", "ALLOW_HTTP", "false")
            matchingFallbacks += "debug"
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

    sourceSets.getByName("androidTest").assets.srcDir(rootProject.file("../tests/fixtures/elevation"))
    sourceSets.getByName("test").resources.srcDir(rootProject.file("../tests/fixtures/elevation"))
    sourceSets.getByName("main").assets.srcDir(bundledShellDirectory)
    sourceSets.getByName("v2Debug").java.srcDir("src/debug/java")
    sourceSets.getByName("v2Debug").manifest.srcFile("src/debug/AndroidManifest.xml")
    sourceSets.getByName("v2Staging").java.srcDir("src/debug/java")
    sourceSets.getByName("v2Staging").res.srcDir(layout.buildDirectory.dir("generated/pr94-staging/res"))
    sourceSets.getByName("v2Staging").assets.srcDir(layout.buildDirectory.dir("generated/pr94-staging/assets"))
    testBuildType = if (providers.gradleProperty("sugargliderV2Staging").isPresent) "v2Staging"
        else if (providers.gradleProperty("sugargliderV2Research").isPresent) "v2Debug" else "debug"
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

    // Experimental Valhalla 3.9.1 migration (PR86); no Play or region publication.
    implementation("io.github.rallista:valhalla-mobile:0.6.4")
    implementation("io.github.rallista:valhalla-models:0.6.0")
    implementation("io.github.rallista:valhalla-models-config:0.6.0")

    // Serialize owned offline actor settings absent from the typed config model.
    implementation("com.squareup.moshi:moshi-kotlin:1.15.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.moshi:moshi-kotlin:1.15.1")
    testImplementation("org.json:json:20250517")
}


// Explicit private test inputs. Only the isolated staging variant receives them.
val prepareV2StagingResources by tasks.registering {
    val certificate = providers.gradleProperty("sugargliderV2StagingCA")
    val catalog = providers.gradleProperty("sugargliderV2StagingCatalog")
    val destination = layout.buildDirectory.dir("generated/pr94-staging")
    inputs.property("certificate", certificate.orElse(""))
    inputs.property("catalog", catalog.orElse(""))
    certificate.orNull?.let { inputs.file(it).withPropertyName("stagingCertificateBytes") }
    catalog.orNull?.let { inputs.file(it).withPropertyName("stagingCatalogBytes") }
    outputs.dir(destination)
    doLast {
        val cert = File(certificate.orNull ?: error("Private staging requires an explicit local CA"))
        val offering = File(catalog.orNull ?: error("Private staging requires a verified V2 catalog"))
        for (source in listOf(cert, offering)) {
            require(source.isAbsolute && source.isFile && !Files.isSymbolicLink(source.toPath()) && source.length() in 1..65_536)
            require(!source.canonicalFile.toPath().startsWith(rootProject.projectDir.parentFile.canonicalFile.toPath()))
        }
        val pem = cert.readText()
        require(pem.startsWith("-----BEGIN CERTIFICATE-----") && !pem.contains("PRIVATE KEY"))
        val root = destination.get().asFile
        root.resolve("res/raw").mkdirs()
        root.resolve("assets/web").mkdirs()
        cert.copyTo(root.resolve("res/raw/pr94_staging_ca.pem"), overwrite = true)
        offering.copyTo(root.resolve("assets/web/offline_region_catalog.json"), overwrite = true)
    }
}
tasks.matching { it.name == "preV2StagingBuild" }.configureEach { dependsOn(prepareV2StagingResources) }
