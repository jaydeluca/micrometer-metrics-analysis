// Tier 2 is split into per-technology runnables: Kafka needs Docker (Testcontainers), gRPC runs
// fully in-process. Each writes its own inventory/micrometer-tier2-*.json; compare.py merges all
// micrometer-*.json. Hence plain `java` + explicit JavaExec tasks rather than the single-mainClass
// `application` plugin.
plugins {
    java
}

dependencies {
    implementation(project(":capture-core"))
    implementation(libs.micrometer.core)

    // Kafka target: a real broker (Testcontainers) + the Kafka client the binder reads.
    implementation(libs.testcontainers)
    implementation(libs.testcontainers.kafka)
    implementation(libs.kafka.clients)

    // gRPC target: in-process server/channel + the interceptors Micrometer instruments.
    implementation(libs.grpc.inprocess)
    implementation(libs.grpc.stub)

    // HTTP client targets: OkHttp + Apache HC5, driven against a JDK built-in HttpServer stub.
    implementation(libs.okhttp)
    implementation(libs.httpclient5)

    // Testcontainers + kafka-clients log via SLF4J; provide a backend.
    runtimeOnly(libs.logback.classic)
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}

val inventoryDir = rootProject.layout.projectDirectory.dir("inventory")
val mmVersion = libs.versions.micrometer.get()

// gRPC: no Docker needed.
tasks.register<JavaExec>("runGrpc") {
    group = "application"
    description = "Capture Micrometer gRPC metrics (in-process server/client)."
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("com.grafana.micrometer.inventory.tier2.GrpcMain")
    systemProperty("micrometer.version", mmVersion)
    systemProperty("inventory.out", inventoryDir.file("micrometer-tier2-grpc.json").asFile.absolutePath)
}

// HTTP clients: no Docker needed (JDK built-in stub server).
tasks.register<JavaExec>("runHttpClient") {
    group = "application"
    description = "Capture Micrometer HTTP-client metrics (OkHttp + Apache HC5 against a JDK stub)."
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("com.grafana.micrometer.inventory.tier2.HttpClientMain")
    systemProperty("micrometer.version", mmVersion)
    systemProperty("inventory.out", inventoryDir.file("micrometer-tier2-httpclient.json").asFile.absolutePath)
}

// Kafka: requires a running Docker daemon.
tasks.register<JavaExec>("runKafka") {
    group = "application"
    description = "Capture Micrometer Kafka client metrics (Testcontainers broker)."
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("com.grafana.micrometer.inventory.tier2.KafkaMain")
    // Modern Docker daemons require API >= 1.40; docker-java's image-inspect path otherwise falls
    // back to 1.32. The `api.version` system property pins it for every client (the env var alone
    // is not honored on that path). Ryuk is disabled to avoid an extra image pull.
    val dockerApi = System.getenv("DOCKER_API_VERSION") ?: "1.44"
    environment("DOCKER_API_VERSION", dockerApi)
    systemProperty("api.version", dockerApi)
    System.getenv("DOCKER_HOST")?.let { environment("DOCKER_HOST", it) }
    environment("TESTCONTAINERS_RYUK_DISABLED", System.getenv("TESTCONTAINERS_RYUK_DISABLED") ?: "true")
    systemProperty("micrometer.version", mmVersion)
    systemProperty("inventory.out", inventoryDir.file("micrometer-tier2-kafka.json").asFile.absolutePath)
}
