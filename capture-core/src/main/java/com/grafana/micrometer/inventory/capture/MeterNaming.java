package com.grafana.micrometer.inventory.capture;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Tag;
import java.util.List;

/**
 * Resolves the externally-visible name, base unit, and tag keys for a captured meter under a given
 * convention. The {@link #IDENTITY} naming reports exactly what Micrometer stored on the
 * {@code Meter.Id} (the {@code micrometer} convention). A harness can supply an alternative — e.g.
 * one backed by the OTLP registry's {@code NamingConvention} — to capture how the same meter would
 * be exported under another convention, without depending on that registry from capture-core.
 */
public interface MeterNaming {

    String name(Meter.Id id);

    String baseUnit(Meter.Id id);

    List<String> tagKeys(Meter.Id id);

    /** Reports the meter exactly as Micrometer stored it. */
    MeterNaming IDENTITY = new MeterNaming() {
        @Override
        public String name(Meter.Id id) {
            return id.getName();
        }

        @Override
        public String baseUnit(Meter.Id id) {
            return id.getBaseUnit();
        }

        @Override
        public List<String> tagKeys(Meter.Id id) {
            return id.getTags().stream().map(Tag::getKey).toList();
        }
    };
}
