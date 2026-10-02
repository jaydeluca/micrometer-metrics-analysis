// Demo module: validate the Micrometer dedup views end-to-end under the real OTel Java agent.
// Not part of the inventory capture pipeline — it produces a runnable app the run-demo.sh
// script launches twice (baseline vs deduped declarative config).
plugins {
    application
}

// MuzzleWindowApp runs against two HikariCP versions, one either side of the agent's muzzle floor
// of [3.0.0,). The version is chosen at launch, so it must NOT be on the installDist runtime
// classpath — run-muzzle-window.sh appends exactly one of these directories instead.
val hikariAboveFloor: Configuration by configurations.creating
val hikariBelowFloor: Configuration by configurations.creating

dependencies {
    implementation(libs.micrometer.core)
    implementation(libs.caffeine) // a Micrometer-only signal (cache.*) the agent does NOT instrument
    // KafkaSurfaceApp only: the agent's kafka-clients-metrics bridge flips default under v3-preview,
    // and a KafkaProducer registers its client metrics at construction, so no broker is needed.
    implementation(libs.kafka.clients)

    // MuzzleWindowApp
    compileOnly(libs.hikaricp)
    implementation(libs.h2)
    hikariAboveFloor(libs.hikaricp) // 5.1.0 — the agent's hikaricp-3.0 module applies
    hikariBelowFloor("com.zaxxer:HikariCP:2.7.9") // muzzle mismatch; Micrometer support since 2.7
}

tasks.register<Sync>("hikariAboveFloorLibs") {
    from(hikariAboveFloor)
    into(layout.buildDirectory.dir("hikari-above-floor"))
}

tasks.register<Sync>("hikariBelowFloorLibs") {
    from(hikariBelowFloor)
    into(layout.buildDirectory.dir("hikari-below-floor"))
}

application {
    mainClass.set("com.grafana.micrometer.demo.DemoApp")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}