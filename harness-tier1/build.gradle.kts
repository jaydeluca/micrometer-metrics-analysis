plugins {
    application
}

dependencies {
    implementation(project(":capture-core"))
    implementation(libs.micrometer.core)
    // No micrometer-registry-otlp here: Tier 0 established the OTLP export naming is identity
    // (0 divergence), so this harness captures only the `micrometer` variant.

    // Tier 1 target libraries the binders read from (the binders themselves ship in micrometer-core).
    implementation(libs.caffeine)
    implementation(libs.guava)
    implementation(libs.commons.pool2)
    implementation(libs.netty.buffer)
    implementation(libs.netty.transport)
    implementation(libs.okhttp)
    implementation(libs.hikaricp)
    runtimeOnly(libs.h2) // HikariCP pool target
}

application {
    mainClass.set("com.grafana.micrometer.inventory.tier1.Tier1Main")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}

tasks.named<JavaExec>("run") {
    systemProperty("micrometer.version", libs.versions.micrometer.get())
    systemProperty(
        "inventory.out",
        rootProject.layout.projectDirectory.dir("inventory").file("micrometer-tier1.json").asFile.absolutePath,
    )
}
