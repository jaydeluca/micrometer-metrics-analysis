package com.grafana.micrometer.experiment;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.distribution.HistogramGauges;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

/**
 * Answers the metric-bridge-interop project's stage-02 questions A1 and A1b empirically.
 *
 * <p>A1: does a {@link MeterFilter} installed on one child of a {@link CompositeMeterRegistry}
 * deny only for that child? The leading design — filter at the agent's bridge registry, before its
 * eager OTel instrument construction — is only correct if the answer is yes.
 *
 * <p>A1b: are meters registered on the composite <em>before</em> a child is added back-filled into
 * that child, and are the child's filters consulted on the back-fill?
 *
 * <p>Plus two follow-ups the source read raised: what a DENY leaves behind in the composite
 * (E4), and whether filters reach synthetic meters (E5).
 */
public final class CompositeFilterExperiment {

    private static final List<String> failures = new ArrayList<>();

    public static void main(String[] args) {
        e1ChildScopedDeny();
        e2FilterRunsBeforeConstruction();
        e3BackfillIsFiltered();
        e3bFilterInstalledAfterRegistration();
        e4WhatADenyLeavesInTheComposite();
        e5SyntheticMeters();

        System.out.println();
        if (failures.isEmpty()) {
            System.out.println("ALL ASSERTIONS PASSED");
        } else {
            System.out.println(failures.size() + " ASSERTION(S) FAILED:");
            failures.forEach(f -> System.out.println("  - " + f));
            System.exit(1);
        }
    }

    // ---------------------------------------------------------------- E1

    /** A child's DENY suppresses the meter in that child only; siblings still get it. */
    private static void e1ChildScopedDeny() {
        section("E1", "a MeterFilter on one child denies for that child only");

        CompositeMeterRegistry composite = new CompositeMeterRegistry();
        CountingRegistry bridgeLike = new CountingRegistry();
        bridgeLike.config().meterFilter(MeterFilter.denyNameStartsWith("jvm."));
        SimpleMeterRegistry sibling = new SimpleMeterRegistry();
        composite.add(bridgeLike);
        composite.add(sibling);

        Counter denied = composite.counter("jvm.gc.pause.count");
        Counter kept = composite.counter("app.orders");
        denied.increment();
        kept.increment(2);

        check("denied meter absent from the filtering child",
                bridgeLike.find("jvm.gc.pause.count").counter() == null);
        check("denied meter present in the sibling",
                sibling.find("jvm.gc.pause.count").counter() != null);
        check("sibling still records the denied meter (value = 1.0)",
                valueOf(sibling.find("jvm.gc.pause.count").counter()) == 1.0);
        check("non-denied meter present in BOTH children",
                bridgeLike.find("app.orders").counter() != null
                        && sibling.find("app.orders").counter() != null);
        check("non-denied meter records in the filtering child (value = 2.0)",
                valueOf(bridgeLike.find("app.orders").counter()) == 2.0);
    }

    // ---------------------------------------------------------------- E2

    /**
     * The filter runs before the child registry constructs the meter. This is the property the
     * bridge needs: {@code OpenTelemetryMeterRegistry} builds its OTel instrument eagerly in the
     * meter constructor, so a DENY has to prevent construction, not just hide the result.
     */
    private static void e2FilterRunsBeforeConstruction() {
        section("E2", "DENY prevents the child from constructing the meter at all");

        CompositeMeterRegistry composite = new CompositeMeterRegistry();
        CountingRegistry bridgeLike = new CountingRegistry();
        bridgeLike.config().meterFilter(MeterFilter.denyNameStartsWith("jvm."));
        composite.add(bridgeLike);
        composite.add(new SimpleMeterRegistry());

        composite.counter("jvm.classes.loaded.count");
        composite.counter("jvm.threads.live.count");
        composite.counter("app.custom");

        check("newCounter() invoked exactly once on the filtering child (for the kept meter only)",
                bridgeLike.newCounterCalls.get() == 1,
                "newCounter calls = " + bridgeLike.newCounterCalls.get());
    }

    // ---------------------------------------------------------------- E3

    /**
     * A1b: meters registered before the child was added are back-filled into it — and the child's
     * filters ARE consulted on the back-fill. Recordings made before the add are not replayed.
     */
    private static void e3BackfillIsFiltered() {
        section("E3", "back-fill of pre-existing meters into a late-added child is filtered");

        CompositeMeterRegistry composite = new CompositeMeterRegistry();
        SimpleMeterRegistry earlySibling = new SimpleMeterRegistry();
        composite.add(earlySibling);

        composite.counter("jvm.memory.used.count").increment(5);
        composite.counter("app.early").increment(3);

        CountingRegistry lateBridge = new CountingRegistry();
        lateBridge.config().meterFilter(MeterFilter.denyNameStartsWith("jvm."));
        composite.add(lateBridge); // filter installed BEFORE the add

        check("pre-existing non-denied meter is back-filled into the late child",
                lateBridge.find("app.early").counter() != null);
        check("pre-existing denied meter is NOT back-filled (child's own filter applied)",
                lateBridge.find("jvm.memory.used.count").counter() == null);
        check("recordings made before the add are not replayed (back-filled value = 0.0)",
                valueOf(lateBridge.find("app.early").counter()) == 0.0,
                "back-filled value = " + valueOf(lateBridge.find("app.early").counter()));
        check("the early sibling still holds the full value (3.0)",
                valueOf(earlySibling.find("app.early").counter()) == 3.0);
    }

    // ---------------------------------------------------------------- E3b

    /** The ordering requirement: a filter installed after registration does not retro-apply. */
    private static void e3bFilterInstalledAfterRegistration() {
        section("E3b", "a filter installed AFTER meters are registered does not retro-apply");

        CompositeMeterRegistry composite = new CompositeMeterRegistry();
        SimpleMeterRegistry child = new SimpleMeterRegistry();
        composite.add(child);
        composite.counter("jvm.late.filter.count").increment();

        child.config().meterFilter(MeterFilter.denyNameStartsWith("jvm.")); // too late

        check("already-registered meter survives a later DENY filter",
                child.find("jvm.late.filter.count").counter() != null);
        check("the same filter does deny a meter registered after it",
                registerAndFind(composite, child, "jvm.after.filter.count") == null);
    }

    // ---------------------------------------------------------------- E4

    /**
     * What a DENY leaves behind: {@code getOrCreateMeter} returns a <em>noop</em> meter to the
     * caller, so the composite still adds a child entry — a noop one. Since composite reads
     * delegate to {@code AbstractCompositeMeter#firstChild()}, a noop child can win and answer
     * reads with 0. Measured across many names because child iteration order is identity-based.
     */
    private static void e4WhatADenyLeavesInTheComposite() {
        section("E4", "what a DENY leaves in the composite, and what composite reads return");

        // Run both add orders: child iteration inside a composite meter is identity-hash based,
        // not insertion based, so the order the registries were added should not matter. Check.
        e4Probe("filtering child added FIRST", true);
        e4Probe("filtering child added LAST", false);
    }

    private static void e4Probe(String label, boolean filteringChildFirst) {
        CompositeMeterRegistry composite = new CompositeMeterRegistry();
        SimpleMeterRegistry bridgeLike = new SimpleMeterRegistry();
        bridgeLike.config().meterFilter(MeterFilter.denyNameStartsWith("jvm."));
        SimpleMeterRegistry sibling = new SimpleMeterRegistry();
        if (filteringChildFirst) {
            composite.add(bridgeLike);
            composite.add(sibling);
        } else {
            composite.add(sibling);
            composite.add(bridgeLike);
        }

        System.out.println("  " + label + ":");
        int probes = 200;
        int readsZeroFromComposite = 0;
        int siblingCorrect = 0;
        for (int i = 0; i < probes; i++) {
            String name = "jvm.probe." + i + ".count";
            composite.counter(name).increment();
            if (valueOf(composite.find(name).counter()) == 0.0) {
                readsZeroFromComposite++;
            }
            if (valueOf(sibling.find(name).counter()) == 1.0) {
                siblingCorrect++;
            }
        }

        check("the sibling recorded every probe correctly (" + label + ")",
                siblingCorrect == probes, siblingCorrect + "/" + probes);
        System.out.printf("    observed: %d/%d composite reads returned 0.0 despite the sibling "
                + "holding 1.0%n", readsZeroFromComposite, probes);
        if (readsZeroFromComposite > 0) {
            System.out.println("    => a denied child leaves a NOOP meter in the composite, and "
                    + "firstChild() can return it");
        } else {
            System.out.println("    => composite reads were unaffected in this run");
        }
    }

    // ---------------------------------------------------------------- E5

    /**
     * Synthetic meters (e.g. the percentile gauges a histogram registers) take a different path:
     * {@code mapId} early-returns for them, so rename filters do not reach them, while
     * {@code accept} still runs.
     */
    private static void e5SyntheticMeters() {
        section("E5", "do filters reach synthetic meters (percentile gauges)?");

        SimpleMeterRegistry renaming = new SimpleMeterRegistry();
        renaming.config().meterFilter(new MeterFilter() {
            @Override
            public Meter.Id map(Meter.Id id) {
                return id.withName("renamed." + id.getName());
            }
        });
        Timer timer = Timer.builder("my.timer").publishPercentiles(0.5, 0.95).register(renaming);
        HistogramGauges.registerWithCommonFormat(timer, renaming);
        timer.record(Duration.ofMillis(5));

        List<String> names = names(renaming);
        System.out.println("    names after a rename filter: " + names);
        check("the timer itself was renamed", names.contains("renamed.my.timer"));
        check("synthetic percentile gauges were NOT renamed again (map skips synthetics)",
                names.stream().anyMatch(n -> n.equals("renamed.my.timer.percentile")),
                "expected 'renamed.my.timer.percentile', got " + names);

        SimpleMeterRegistry denying = new SimpleMeterRegistry();
        denying.config().meterFilter(MeterFilter.deny(id -> id.getName().endsWith(".percentile")));
        Timer timer2 = Timer.builder("my.timer").publishPercentiles(0.5, 0.95).register(denying);
        HistogramGauges.registerWithCommonFormat(timer2, denying);
        timer2.record(Duration.ofMillis(5));

        List<String> denyNames = names(denying);
        System.out.println("    names after a deny filter on '.percentile': " + denyNames);
        check("DENY does reach synthetic meters",
                denyNames.stream().noneMatch(n -> n.endsWith(".percentile")),
                denyNames.toString());
    }

    // ---------------------------------------------------------------- helpers

    /** A registry that counts how many times it is asked to construct a counter. */
    private static final class CountingRegistry extends SimpleMeterRegistry {
        final AtomicInteger newCounterCalls = new AtomicInteger();

        @Override
        protected Counter newCounter(Meter.Id id) {
            newCounterCalls.incrementAndGet();
            return super.newCounter(id);
        }
    }

    private static Counter registerAndFind(CompositeMeterRegistry composite, MeterRegistry child,
            String name) {
        composite.counter(name).increment();
        return child.find(name).counter();
    }

    private static double valueOf(Counter counter) {
        return counter == null ? Double.NaN : counter.count();
    }

    private static List<String> names(MeterRegistry registry) {
        return registry.getMeters().stream()
                .map(m -> m.getId().getName())
                .distinct()
                .sorted()
                .collect(Collectors.toList());
    }

    private static void section(String id, String title) {
        System.out.println();
        System.out.println(id + " — " + title);
    }

    private static void check(String what, boolean ok) {
        check(what, ok, null);
    }

    private static void check(String what, boolean ok, String detail) {
        System.out.println("    [" + (ok ? "PASS" : "FAIL") + "] " + what
                + (detail == null ? "" : "  (" + detail + ")"));
        if (!ok) {
            failures.add(what + (detail == null ? "" : " — " + detail));
        }
    }

    private CompositeFilterExperiment() {}
}
