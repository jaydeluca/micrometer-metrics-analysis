package com.grafana.micrometer.inventory.model;

/**
 * Which naming convention a binder was constructed under.
 *
 * <p>Micrometer's default dotted names are the {@link #MICROMETER} variant. The {@link #OTEL}
 * variant is reserved for binders that can be told to emit OpenTelemetry semantic-convention
 * names. As of Micrometer 1.15.x the JVM/system binders expose no such switch (their only
 * non-default constructor argument is {@code Iterable<Tag>}), so this is captured machinery
 * waiting for an API that emits semconv names natively; see the capture report for the finding.
 */
public enum ConventionVariant {
    MICROMETER("micrometer"),
    OTEL("otel");

    private final String json;

    ConventionVariant(String json) {
        this.json = json;
    }

    public String json() {
        return json;
    }
}
