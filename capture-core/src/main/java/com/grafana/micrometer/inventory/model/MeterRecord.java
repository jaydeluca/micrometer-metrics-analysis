package com.grafana.micrometer.inventory.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.List;

/**
 * One inventory entry: a distinct Meter as read out of a {@code MeterRegistry}.
 *
 * <p>{@code meterType} is the coarse {@code Meter.Type} (COUNTER/GAUGE/TIMER/...), which collapses
 * FunctionCounter into COUNTER and TimeGauge/FunctionTimer into GAUGE/TIMER — the right
 * granularity for comparing against an OpenTelemetry {@code data_type}. {@code baseUnit} and
 * {@code description} are kept even when null so coverage gaps stay visible.
 *
 * <p>Field declaration order is the JSON serialization order.
 */
public record MeterRecord(
        String name,
        String meterType,
        String baseUnit,
        List<String> tagKeys,
        String description,
        String emittedBy,
        String technology,
        String conventionVariant,
        boolean deprecated,
        @JsonInclude(JsonInclude.Include.NON_NULL) String deprecatedSince,
        int captureTier,
        String micrometerVersion,
        String jdk,
        String source) {
}
