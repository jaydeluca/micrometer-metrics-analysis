package com.grafana.micrometer.inventory.capture;

import com.grafana.micrometer.inventory.model.ConventionVariant;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;
import java.util.function.Consumer;
import java.util.function.Supplier;

/**
 * Describes how to exercise one binder under one convention variant.
 *
 * <p>{@code binderClass} is the declared class (used for {@code emittedBy}, {@code @Deprecated}
 * reflection, and failure labelling) and is decoupled from {@code factory} so we can report a
 * meaningful label even when construction throws. {@code activity} drives the single observation
 * needed to materialize lazily-created meters (a Timer/DistributionSummary exposes its tag keys
 * only after one recording); it may be null for binders whose meters are eager gauges.
 *
 * <p>{@code naming} resolves the externally-visible name/unit/tag-keys. The default
 * {@link MeterNaming#IDENTITY} reports Micrometer's stored names ({@code micrometer} variant); a
 * harness can attach an alternative (e.g. OTLP-registry naming) and flip {@code variant} to
 * capture how the same binder's meters would be exported under another convention.
 *
 * <p>{@code emittedByOverride} is for the rare source that does not ship as a {@link MeterBinder} —
 * e.g. HikariCP's {@code MicrometerMetricsTrackerFactory}, which we adapt behind a synthetic
 * {@code MeterBinder}. When set it replaces the wrapper class name in {@code emittedBy()} so the
 * inventory attributes the meters to their real source. {@code binderClass} still drives the
 * {@code @Deprecated} reflection and failure labelling.
 */
public record BinderSpec(
        String technology,
        ConventionVariant variant,
        int tier,
        Class<? extends MeterBinder> binderClass,
        Supplier<MeterBinder> factory,
        Consumer<MeterRegistry> activity,
        MeterNaming naming,
        String emittedByOverride) {

    /** A binder under the default Micrometer convention with no activity to drive. */
    public static BinderSpec of(
            String technology, int tier, Class<? extends MeterBinder> binderClass, Supplier<MeterBinder> factory) {
        return new BinderSpec(
                technology, ConventionVariant.MICROMETER, tier, binderClass, factory, null, MeterNaming.IDENTITY, null);
    }

    public BinderSpec withActivity(Consumer<MeterRegistry> activity) {
        return new BinderSpec(technology, variant, tier, binderClass, factory, activity, naming, emittedByOverride);
    }

    /** Re-target this spec at another convention, supplying the naming that resolves its names. */
    public BinderSpec as(ConventionVariant variant, MeterNaming naming) {
        return new BinderSpec(technology, variant, tier, binderClass, factory, activity, naming, emittedByOverride);
    }

    /** Attribute the captured meters to {@code source} instead of the (possibly synthetic) binder class. */
    public BinderSpec emittedBy(String source) {
        return new BinderSpec(technology, variant, tier, binderClass, factory, activity, naming, source);
    }

    public String emittedBy() {
        return emittedByOverride != null ? emittedByOverride : binderClass.getName();
    }
}
