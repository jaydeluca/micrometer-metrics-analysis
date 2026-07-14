plugins {
    `java-library`
}

dependencies {
    // micrometer-core is part of the public API: callers hand us Meters and binders.
    api(libs.micrometer.core)
    implementation(libs.jackson.databind)
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
