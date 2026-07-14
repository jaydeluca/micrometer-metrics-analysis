package com.grafana.micrometer.inventory.capture;

import java.time.Instant;

/**
 * Run-level facts stamped onto every record and into the header. Resolved from the JVM and a couple
 * of well-known system properties / env vars so the harness stays free of hard-coded versions.
 */
public record RunMeta(
        String micrometerVersion,
        String gitSha,
        String capturedAt,
        String jdk,
        String os,
        String source) {

    /** Resolve from the running JVM. The Micrometer version is injected by Gradle as a property. */
    public static RunMeta detect() {
        String mm = System.getProperty("micrometer.version", "unknown");
        String sha = System.getenv("MICROMETER_GIT_SHA"); // null unless built from source
        String jdk = String.valueOf(Runtime.version().feature());
        String os = System.getProperty("os.name") + " " + System.getProperty("os.arch");
        return new RunMeta(mm, sha, Instant.now().toString(), jdk, os, "runtime");
    }
}
