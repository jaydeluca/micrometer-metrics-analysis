// Tier 3: a real Spring Boot app whose Actuator autoconfiguration populates one MeterRegistry.
// We don't use the Spring Boot Gradle plugin (no fat jar needed) — just its dependency BOM, and a
// plain JavaExec run task that boots the app, drives traffic, dumps the registry, and exits.
plugins {
    java
}

dependencies {
    implementation(project(":capture-core"))
    implementation(platform(libs.spring.boot.dependencies)) // BOM: manages Spring + Micrometer versions

    implementation("org.springframework.boot:spring-boot-starter-web")        // http.server.requests, tomcat.*
    implementation("org.springframework.boot:spring-boot-starter-actuator")   // MeterRegistry + binders + auto-config
    implementation("org.springframework.boot:spring-boot-starter-jdbc")       // DataSource → jdbc.connections.*
    runtimeOnly("com.h2database:h2")
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}

tasks.register<JavaExec>("runSpring") {
    group = "application"
    description = "Boot a Spring app, drive server+client+DB traffic, dump the Actuator MeterRegistry."
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("com.grafana.micrometer.inventory.tier3.Tier3App")
    systemProperty("micrometer.version", libs.versions.micrometer.get())
    systemProperty(
        "inventory.out",
        rootProject.layout.projectDirectory.dir("inventory").file("micrometer-tier3.json").asFile.absolutePath,
    )
}
