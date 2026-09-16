// Experiment module: does a MeterFilter installed on ONE child of a CompositeMeterRegistry
// deny only for that child? This is the load-bearing assumption behind the metric-bridge-interop
// project's leading design (filter at the bridge registry, before eager OTel instrument
// construction). Not part of the inventory capture pipeline.
plugins {
    application
}

dependencies {
    implementation(libs.micrometer.core)
}

application {
    mainClass.set("com.grafana.micrometer.experiment.CompositeFilterExperiment")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}