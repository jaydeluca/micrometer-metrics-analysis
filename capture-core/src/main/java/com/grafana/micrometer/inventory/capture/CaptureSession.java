package com.grafana.micrometer.inventory.capture;

import com.grafana.micrometer.inventory.model.Inventory;
import com.grafana.micrometer.inventory.model.InventoryHeader;
import com.grafana.micrometer.inventory.model.MeterRecord;
import com.grafana.micrometer.inventory.model.TierCoverage;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.binder.MeterBinder;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * Drives the core capture mechanism for a set of {@link BinderSpec}s:
 *
 * <pre>
 *   construct binder -&gt; bindTo(SimpleMeterRegistry) -&gt; drive one observation
 *     -&gt; for each Meter: record name/type/baseUnit/description/tagKeys
 *     -&gt; stamp emittedBy/technology/conventionVariant/deprecated/tier/version/jdk/source
 * </pre>
 *
 * Each binder gets its own registry so {@code emittedBy} attribution is unambiguous. Construction
 * and binding are guarded: a failure is recorded in the tier coverage rather than aborting the run.
 */
public final class CaptureSession {

    private final RunMeta meta;
    private final List<MeterRecord> records = new ArrayList<>();
    private final Map<Integer, Coverage> coverageByTier = new TreeMap<>();

    public CaptureSession(RunMeta meta) {
        this.meta = meta;
    }

    public void capture(BinderSpec spec) {
        Coverage cov = coverageByTier.computeIfAbsent(spec.tier(), Coverage::new);
        cov.attempted++;

        // Deprecation is deterministic: read it straight off the declared binder class.
        boolean deprecated = spec.binderClass().isAnnotationPresent(Deprecated.class);
        String deprecatedSince = null;
        if (deprecated) {
            String since = spec.binderClass().getAnnotation(Deprecated.class).since();
            deprecatedSince = since.isEmpty() ? null : since;
        }

        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            MeterBinder binder = spec.factory().get();
            binder.bindTo(registry);
            if (spec.activity() != null) {
                spec.activity().accept(registry);
            }
            for (Meter meter : registry.getMeters()) {
                records.add(toRecord(meter, spec, deprecated, deprecatedSince));
            }
            cov.succeeded++;
            cov.meters += registry.getMeters().size();
            closeQuietly(binder);
        } catch (Throwable t) {
            cov.failed++;
            cov.failures.add(spec.emittedBy() + " [" + spec.variant().json() + "]: " + describe(t));
        } finally {
            registry.close();
        }
    }

    /**
     * Capture every meter already present in a populated registry — the Tier 3 path, where a wired
     * Spring Boot context (not an individual binder) is the source. Each meter's technology bucket is
     * resolved from its name via {@code technologyOf}; all rows share {@code emittedBy} (the source is
     * Spring autoconfiguration, not a single class) and the {@code micrometer} convention. The whole
     * registry counts as one "binder" in the tier coverage.
     */
    public void captureRegistry(
            io.micrometer.core.instrument.MeterRegistry registry,
            int tier,
            String emittedBy,
            java.util.function.Function<String, String> technologyOf) {
        Coverage cov = coverageByTier.computeIfAbsent(tier, Coverage::new);
        cov.attempted++;
        for (Meter meter : registry.getMeters()) {
            Meter.Id id = meter.getId();
            records.add(new MeterRecord(
                    id.getName(),
                    id.getType().name(),
                    id.getBaseUnit(),
                    id.getTags().stream().map(io.micrometer.core.instrument.Tag::getKey).toList(),
                    id.getDescription(),
                    emittedBy,
                    technologyOf.apply(id.getName()),
                    "micrometer",
                    false,
                    null,
                    tier,
                    meta.micrometerVersion(),
                    meta.jdk(),
                    meta.source()));
            cov.meters++;
        }
        cov.succeeded++;
    }

    private MeterRecord toRecord(Meter meter, BinderSpec spec, boolean deprecated, String deprecatedSince) {
        Meter.Id id = meter.getId();
        MeterNaming naming = spec.naming();
        return new MeterRecord(
                naming.name(id),
                id.getType().name(), // coarse Meter.Type
                naming.baseUnit(id),
                naming.tagKeys(id),
                id.getDescription(),
                spec.emittedBy(),
                spec.technology(),
                spec.variant().json(),
                deprecated,
                deprecatedSince,
                spec.tier(),
                meta.micrometerVersion(),
                meta.jdk(),
                meta.source());
    }

    /** Build the sorted, de-duplicated inventory. */
    public Inventory build() {
        // Many concrete meters share an identity (e.g. jvm.memory.used per area/id); they produce
        // value-equal records, so a set collapses them to one inventory entry.
        List<MeterRecord> deduped = new ArrayList<>(new LinkedHashSet<>(records));
        deduped.sort(Comparator.comparing(MeterRecord::technology)
                .thenComparing(MeterRecord::emittedBy)
                .thenComparing(MeterRecord::conventionVariant)
                .thenComparing(MeterRecord::name)
                .thenComparing(r -> String.join(",", r.tagKeys())));

        List<TierCoverage> coverage = coverageByTier.values().stream()
                .map(Coverage::toRecord)
                .toList();

        InventoryHeader header = new InventoryHeader(
                meta.micrometerVersion(),
                meta.gitSha(),
                meta.capturedAt(),
                meta.jdk(),
                meta.os(),
                deduped.size(),
                coverage);
        return new Inventory(header, deduped);
    }

    private static void closeQuietly(MeterBinder binder) {
        if (binder instanceof AutoCloseable closeable) {
            try {
                closeable.close();
            } catch (Exception ignored) {
                // best-effort cleanup of listener-registering binders (GC notifications, JFR streams)
            }
        }
    }

    private static String describe(Throwable t) {
        String msg = t.getMessage();
        return t.getClass().getSimpleName() + (msg == null ? "" : ": " + msg);
    }

    /** Mutable per-tier accumulator, frozen into a {@link TierCoverage} at build time. */
    private static final class Coverage {
        final int tier;
        int attempted;
        int succeeded;
        int failed;
        int meters;
        final List<String> failures = new ArrayList<>();

        Coverage(int tier) {
            this.tier = tier;
        }

        TierCoverage toRecord() {
            return new TierCoverage(tier, attempted, succeeded, failed, meters, List.copyOf(failures));
        }
    }
}
