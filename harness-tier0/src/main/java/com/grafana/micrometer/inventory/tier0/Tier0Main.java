package com.grafana.micrometer.inventory.tier0;

import com.grafana.micrometer.inventory.capture.BinderSpec;
import com.grafana.micrometer.inventory.capture.CaptureSession;
import com.grafana.micrometer.inventory.capture.InventoryWriter;
import com.grafana.micrometer.inventory.capture.RunMeta;
import com.grafana.micrometer.inventory.model.ConventionVariant;
import com.grafana.micrometer.inventory.model.Inventory;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.jvm.ClassLoaderMetrics;
import io.micrometer.core.instrument.binder.jvm.ExecutorServiceMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmCompilationMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmGcMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmHeapPressureMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmInfoMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmMemoryMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmThreadDeadlockMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmThreadMetrics;
import io.micrometer.core.instrument.binder.logging.Log4j2Metrics;
import io.micrometer.core.instrument.binder.logging.LogbackMetrics;
import io.micrometer.core.instrument.binder.system.FileDescriptorMetrics;
import io.micrometer.core.instrument.binder.system.ProcessorMetrics;
import io.micrometer.core.instrument.binder.system.UptimeMetrics;
import io.micrometer.java21.instrument.binder.jdk.VirtualThreadMetrics;
import java.io.File;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.core.config.Configurator;

/**
 * Tier 0 harness: pure-JVM / system / logging / executor binders, no external dependencies.
 *
 * <p>Note on convention variants: the project intends to capture each JVM/CPU binder under both the
 * default Micrometer convention and an opt-in OpenTelemetry semconv convention. Micrometer 1.15.x
 * exposes no such switch on these binders — their only non-default constructor argument is
 * {@code Iterable<Tag>}, and OTel naming exists solely in the OTLP <em>registry</em> export layer
 * (which rewrites names at publish time and never changes {@code Meter.Id.getName()} read here). So
 * every record below is the {@code micrometer} variant; the {@code otel} variant is a captured gap,
 * not a fabricated row. The machinery (the {@code conventionVariant} field, {@code withVariant})
 * is in place for the day a binder gains a native semconv mode.
 */
public final class Tier0Main {

    public static void main(String[] args) throws Exception {
        Path out = Path.of(System.getProperty("inventory.out", "inventory/micrometer-tier0.json"));

        CaptureSession session = new CaptureSession(RunMeta.detect());

        // Executors are created once so the factory and the activity closure share the same instance.
        ThreadPoolExecutor threadPool =
                new ThreadPoolExecutor(1, 2, 0L, TimeUnit.MILLISECONDS, new LinkedBlockingQueue<>());
        ForkJoinPool forkJoinPool = new ForkJoinPool(2);

        // Each binder is captured twice: under Micrometer's stored names, and under the OTLP
        // registry's export naming (the otel variant). This makes "what name does Micrometer
        // actually emit over OTLP?" a captured fact per binder.
        OtlpMeterNaming otlpNaming = new OtlpMeterNaming();
        List<BinderSpec> base = specs(threadPool, forkJoinPool);
        for (BinderSpec spec : base) {
            session.capture(spec);
        }
        for (BinderSpec spec : base) {
            session.capture(spec.as(ConventionVariant.OTEL, otlpNaming));
        }

        threadPool.shutdownNow();
        forkJoinPool.shutdownNow();

        Inventory inventory = session.build();
        InventoryWriter writer = new InventoryWriter();
        writer.write(inventory, out);
        writer.printSummary(inventory, out);
        reportOtelDivergence(inventory);
    }

    /**
     * Report how often the OTLP export name differs from the Micrometer stored name — the whole
     * point of capturing the otel variant. If this stays at 0, Micrometer's OTLP export preserves
     * its dotted names verbatim and the otel rows carry no naming signal of their own.
     */
    private static void reportOtelDivergence(Inventory inventory) {
        var micrometer = new java.util.HashMap<List<String>, com.grafana.micrometer.inventory.model.MeterRecord>();
        for (var r : inventory.meters()) {
            if ("micrometer".equals(r.conventionVariant())) {
                micrometer.put(List.of(r.emittedBy(), str(r.description()), r.meterType()), r);
            }
        }
        int total = 0;
        int diverged = 0;
        for (var r : inventory.meters()) {
            if (!"otel".equals(r.conventionVariant())) {
                continue;
            }
            var mm = micrometer.get(List.of(r.emittedBy(), str(r.description()), r.meterType()));
            if (mm == null) {
                continue;
            }
            total++;
            if (!mm.name().equals(r.name()) || !mm.tagKeys().equals(r.tagKeys())) {
                diverged++;
            }
        }
        System.out.printf(
                "otel naming (via OtlpMeterRegistry): %d/%d names diverge from micrometer%s%n",
                diverged, total, diverged == 0 ? "  → OTLP export preserves Micrometer dotted names verbatim" : "");
    }

    private static String str(String s) {
        return s == null ? "" : s;
    }

    private static List<BinderSpec> specs(ThreadPoolExecutor threadPool, ForkJoinPool forkJoinPool) {
        List<BinderSpec> specs = new ArrayList<>();
        int tier = 0;

        // ---- pure JVM (eager gauges; no activity needed) ----
        specs.add(BinderSpec.of("jvm", tier, JvmMemoryMetrics.class, JvmMemoryMetrics::new));
        specs.add(BinderSpec.of("jvm", tier, JvmThreadMetrics.class, JvmThreadMetrics::new));
        specs.add(BinderSpec.of("jvm", tier, ClassLoaderMetrics.class, ClassLoaderMetrics::new));
        specs.add(BinderSpec.of("jvm", tier, JvmCompilationMetrics.class, JvmCompilationMetrics::new));
        specs.add(BinderSpec.of("jvm", tier, JvmInfoMetrics.class, JvmInfoMetrics::new));
        specs.add(BinderSpec.of("jvm", tier, JvmHeapPressureMetrics.class, JvmHeapPressureMetrics::new));
        specs.add(BinderSpec.of("jvm", tier, JvmThreadDeadlockMetrics.class, JvmThreadDeadlockMetrics::new));

        // JvmGcMetrics: pause timers materialize only after a GC notification arrives.
        specs.add(BinderSpec.of("jvm", tier, JvmGcMetrics.class, JvmGcMetrics::new)
                .withActivity(reg -> {
                    System.gc();
                    sleep(500);
                }));

        // ExecutorServiceMetrics over a ThreadPoolExecutor and a ForkJoinPool (different meter sets).
        specs.add(BinderSpec.of(
                        "executor",
                        tier,
                        ExecutorServiceMetrics.class,
                        () -> new ExecutorServiceMetrics(threadPool, "tier0-tpe", List.of()))
                .withActivity(reg -> runOne(threadPool::submit)));
        specs.add(BinderSpec.of(
                        "executor",
                        tier,
                        ExecutorServiceMetrics.class,
                        () -> new ExecutorServiceMetrics(forkJoinPool, "tier0-fjp", List.of()))
                .withActivity(reg -> runOne(forkJoinPool::submit)));

        // ---- system ----
        specs.add(BinderSpec.of("system", tier, ProcessorMetrics.class, ProcessorMetrics::new));
        specs.add(BinderSpec.of("system", tier, FileDescriptorMetrics.class, FileDescriptorMetrics::new));
        specs.add(BinderSpec.of("system", tier, UptimeMetrics.class, UptimeMetrics::new));
        File here = new File(System.getProperty("user.dir"));
        specs.add(BinderSpec.of(
                "system",
                tier,
                io.micrometer.core.instrument.binder.system.DiskSpaceMetrics.class,
                () -> new io.micrometer.core.instrument.binder.system.DiskSpaceMetrics(here)));
        // The older jvm.DiskSpaceMetrics is @Deprecated — included to prove the reflection capture.
        specs.add(BinderSpec.of(
                "system",
                tier,
                io.micrometer.core.instrument.binder.jvm.DiskSpaceMetrics.class,
                () -> new io.micrometer.core.instrument.binder.jvm.DiskSpaceMetrics(here)));

        // ---- logging: drive one log line per level so the per-level counters exist ----
        specs.add(BinderSpec.of("logging", tier, LogbackMetrics.class, LogbackMetrics::new)
                .withActivity(reg -> emitLogbackLines()));
        specs.add(BinderSpec.of("logging", tier, Log4j2Metrics.class, Log4j2Metrics::new)
                .withActivity(reg -> emitLog4j2Lines()));

        // ---- JDK 21 virtual threads (JFR-backed; meters register at bind, exercise to be safe) ----
        specs.add(BinderSpec.of("jvm", tier, VirtualThreadMetrics.class, VirtualThreadMetrics::new)
                .withActivity(reg -> {
                    try {
                        Thread.ofVirtual().start(() -> {}).join();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                    sleep(300);
                }));

        return specs;
    }

    private static void emitLogbackLines() {
        ch.qos.logback.classic.Logger root = (ch.qos.logback.classic.Logger)
                org.slf4j.LoggerFactory.getLogger(org.slf4j.Logger.ROOT_LOGGER_NAME);
        ch.qos.logback.classic.Level previous = root.getLevel();
        root.setLevel(ch.qos.logback.classic.Level.TRACE);
        org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger("inventory.sample.logback");
        log.error("e");
        log.warn("w");
        log.info("i");
        log.debug("d");
        log.trace("t");
        root.setLevel(previous);
    }

    private static void emitLog4j2Lines() {
        Configurator.setRootLevel(org.apache.logging.log4j.Level.TRACE);
        org.apache.logging.log4j.Logger log = LogManager.getLogger("inventory.sample.log4j2");
        log.error("e");
        log.warn("w");
        log.info("i");
        log.debug("d");
        log.trace("t");
    }

    /** Submit one no-op task and wait for it, so execution-time timers get a single recording. */
    private static void runOne(java.util.function.Function<Runnable, java.util.concurrent.Future<?>> submit) {
        try {
            submit.apply(() -> {}).get(2, TimeUnit.SECONDS);
        } catch (Exception ignored) {
            // a missing data point just means fewer tag keys; not fatal to the inventory
        }
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private Tier0Main() {}
}
