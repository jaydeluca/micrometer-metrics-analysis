// demo-convention: does opting into Spring's *semconv-named* observation convention defeat a
// drop-set keyed on Micrometer's historical metric name? (metric-bridge-interop, stage 02 item A3.)
//
// Deliberately a separate module from demo-dedup rather than another app inside it: this needs
// Spring Boot 4 / spring-framework 7 on the runtime classpath, and demo-dedup's three existing
// experiments all launch from one shared `build/install/demo-dedup/lib/*`. Putting Spring there
// would change the classpath — and therefore the agent's instrumentation decisions — for the
// runs that already carry verified assertion counts (35/35, 15/15).
plugins {
    application
}

dependencies {
    // Boot 4 BOM: spring-framework 7.0.x, where OpenTelemetryServerRequestObservationConvention lives.
    implementation(platform(libs.springBoot4.dependencies))

    implementation("org.springframework.boot:spring-boot-starter-web")      // http.server.requests
    // Boot 4 modularized actuator, but the starter still pulls spring-boot-starter-micrometer-metrics,
    // which supplies the MeterRegistry/Clock beans the agent's
    // OpenTelemetryMeterRegistryAutoConfiguration is @ConditionalOnBean(Clock.class) on.
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}

application {
    mainClass.set("com.grafana.micrometer.convention.ConventionProbeApp")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
    // Spring resolves @PathVariable/@RequestParam names reflectively. The Boot Gradle plugin sets
    // this; we only use the BOM, so set it here — without it every request 500s on parameter-name
    // resolution and the probe measures an error path instead of the convention.
    options.compilerArgs.add("-parameters")
}
