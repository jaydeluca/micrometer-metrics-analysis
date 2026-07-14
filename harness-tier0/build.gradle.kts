plugins {
    application
}

dependencies {
    implementation(project(":capture-core"))
    implementation(libs.micrometer.core)
    implementation(libs.micrometer.java21) // VirtualThreadMetrics (JDK 21+)
    implementation(libs.micrometer.registry.otlp) // source of the OTLP export naming convention

    // Logging binders need a real logging backend on the classpath.
    implementation(libs.logback.classic)  // also provides the SLF4J binding
    implementation(libs.log4j.core)
    implementation(libs.log4j.api)
}

application {
    mainClass.set("com.grafana.micrometer.inventory.tier0.Tier0Main")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}

tasks.named<JavaExec>("run") {
    // The Micrometer version is known only to Gradle; stamp it into the output via a system property.
    systemProperty("micrometer.version", libs.versions.micrometer.get())
    // Write the committed inventory file at the repo root regardless of the module working dir.
    systemProperty(
        "inventory.out",
        rootProject.layout.projectDirectory.dir("inventory").file("micrometer-tier0.json").asFile.absolutePath,
    )
}
