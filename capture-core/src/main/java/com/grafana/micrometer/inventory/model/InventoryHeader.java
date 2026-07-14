package com.grafana.micrometer.inventory.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.List;

/**
 * Top-of-file stamp describing the run that produced this inventory. {@code gitSha} is populated
 * only when Micrometer is built from source (env {@code MICROMETER_GIT_SHA}); for a pinned release
 * dependency it is null.
 */
public record InventoryHeader(
        String micrometerVersion,
        @JsonInclude(JsonInclude.Include.NON_NULL) String gitSha,
        String capturedAt,
        String jdk,
        String os,
        int totalMeters,
        List<TierCoverage> coverage) {
}
