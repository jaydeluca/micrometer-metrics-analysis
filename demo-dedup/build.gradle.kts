// Demo module: validate the Micrometer dedup views end-to-end under the real OTel Java agent.
// Not part of the inventory capture pipeline — it produces a runnable app the run-demo.sh
// script launches twice (baseline vs deduped declarative config).
plugins {
    application
}

dependencies {
    implementation(libs.micrometer.core)
    implementation(libs.caffeine) // a Micrometer-only signal (cache.*) the agent does NOT instrument
}

application {
    mainClass.set("com.grafana.micrometer.demo.DemoApp")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}