package com.grafana.micrometer.inventory.tier0;

import com.grafana.micrometer.inventory.capture.MeterNaming;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Tag;
import io.micrometer.core.instrument.config.NamingConvention;
import io.micrometer.registry.otlp.OtlpMeterRegistry;
import java.util.List;

/**
 * The {@code otel} convention variant, derived from the OTLP registry's {@link NamingConvention}.
 *
 * <p>This is how Micrometer would name a meter when exported over OTLP — i.e. what an
 * OpenTelemetry collector receives. We borrow only the registry's naming convention (a pure
 * function of name/type/baseUnit) rather than binding to a live {@link OtlpMeterRegistry}, so no
 * network publisher is ever started. The registry is constructed solely to read its convention and
 * is closed immediately.
 */
public final class OtlpMeterNaming implements MeterNaming {

    private final NamingConvention convention;

    public OtlpMeterNaming() {
        OtlpMeterRegistry registry = new OtlpMeterRegistry();
        try {
            this.convention = registry.config().namingConvention();
        } finally {
            registry.close(); // never started; close defensively in case construction armed a scheduler
        }
    }

    @Override
    public String name(Meter.Id id) {
        return convention.name(id.getName(), id.getType(), id.getBaseUnit());
    }

    @Override
    public String baseUnit(Meter.Id id) {
        return id.getBaseUnit();
    }

    @Override
    public List<String> tagKeys(Meter.Id id) {
        return id.getTags().stream().map(Tag::getKey).map(convention::tagKey).toList();
    }
}
