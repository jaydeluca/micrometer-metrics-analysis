package com.grafana.micrometer.demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.Measurement;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.Statistic;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.binder.jvm.JvmGcMetrics;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Exercises <b>one meter of every Micrometer type</b> against {@link Metrics#globalRegistry}, so the
 * full emitted surface of the agent's {@code micrometer-1.5} bridge can be captured and diffed
 * across {@code otel.instrumentation.common.v3-preview} on/off (work-stream 01, task 1.3).
 *
 * <p>Distinct from {@link DemoApp}, which binds real binders to validate the dedup views. This one
 * cares only about the <i>shape</i> of the bridge's output: which instrument names, units, and data
 * types appear for each Micrometer meter type. Every metric is named {@code demo.*} so nothing here
 * collides with the agent's native instrumentation.
 *
 * <p>The three v3-preview-sensitive cases, per source at {@code a094514f76}:
 *
 * <ul>
 *   <li>{@code Timer} and {@code DistributionSummary} emit a {@code <name>.max} companion gauge
 *       only when {@code emitMaxGauge} — i.e. {@code !v3Preview}
 *       ({@code OpenTelemetryMeterRegistry.java:74}).
 *   <li>Custom {@code Meter}s build {@code <name>.<statistic>} in a different order under
 *       v3-preview ({@code Bridging.java:70}) — observable only when the naming convention is not
 *       the identity, i.e. under {@code prometheus_mode}. Hence {@code demo.custom.*} carries a
 *       base unit and a non-{@code OTHER} type, which is what
 *       {@code PrometheusModeNamingConvention} keys on.
 *   <li>{@code JvmGcMetrics} is bound as a control: a real binder whose {@code jvm.gc.pause} Timer
 *       must show the same {@code .max} delta as the synthetic one.
 * </ul>
 */
public final class BridgeSurfaceApp {

  public static void main(String[] args) throws Exception {
    long runMillis = Long.getLong("demo.run.millis", 12_000L);

    // --- one meter of each Micrometer type -------------------------------------------------
    Counter counter =
        Counter.builder("demo.counter").baseUnit("bytes").description("a counter").register(Metrics.globalRegistry);

    AtomicLong gaugeSource = new AtomicLong();
    Gauge.builder("demo.gauge", gaugeSource, AtomicLong::doubleValue)
        .baseUnit("bytes")
        .description("a gauge")
        .register(Metrics.globalRegistry);

    Timer timer = Timer.builder("demo.timer").description("a timer").register(Metrics.globalRegistry);

    DistributionSummary summary =
        DistributionSummary.builder("demo.summary")
            .baseUnit("bytes")
            .description("a distribution summary")
            .register(Metrics.globalRegistry);

    LongTaskTimer longTaskTimer =
        LongTaskTimer.builder("demo.longtask")
            .description("a long task timer")
            .register(Metrics.globalRegistry);

    AtomicLong functionCounterSource = new AtomicLong();
    io.micrometer.core.instrument.FunctionCounter.builder(
            "demo.function.counter", functionCounterSource, AtomicLong::doubleValue)
        .baseUnit("bytes")
        .description("a function counter")
        .register(Metrics.globalRegistry);

    AtomicLong functionTimerCount = new AtomicLong();
    io.micrometer.core.instrument.FunctionTimer.builder(
            "demo.function.timer",
            functionTimerCount,
            AtomicLong::get,
            c -> c.doubleValue() * 10.0,
            TimeUnit.MILLISECONDS)
        .description("a function timer")
        .register(Metrics.globalRegistry);

    // Custom Meter, GAUGE-typed with a base unit: under prometheus_mode the naming convention
    // appends the base unit, so the v2/v3 statistic-suffix ordering becomes visible.
    Meter.builder(
            "demo.custom",
            Meter.Type.GAUGE,
            Arrays.asList(
                new Measurement(() -> 1.0, Statistic.VALUE),
                new Measurement(() -> 2.0, Statistic.TOTAL_TIME),
                new Measurement(() -> 3.0, Statistic.COUNT)))
        .baseUnit("bytes")
        .description("a custom meter")
        .register(Metrics.globalRegistry);

    // Custom Meter, TIMER-typed with no base unit: prometheus_mode appends ".seconds" instead,
    // so the same ordering delta shows up on a metric where no unit is involved.
    Meter.builder(
            "demo.customtimer",
            Meter.Type.TIMER,
            Arrays.asList(
                new Measurement(() -> 4.0, Statistic.TOTAL_TIME),
                new Measurement(() -> 5.0, Statistic.COUNT)))
        .description("a custom timer meter")
        .register(Metrics.globalRegistry);

    // Control: a real binder, so the .max delta is observed on production code too.
    new JvmGcMetrics().bindTo(Metrics.globalRegistry);

    System.out.println("[surface] generating activity for " + runMillis + "ms ...");
    long deadline = System.currentTimeMillis() + runMillis;
    long i = 0;
    LongTaskTimer.Sample sample = longTaskTimer.start();
    while (System.currentTimeMillis() < deadline) {
      counter.increment(3);
      gaugeSource.set(i % 100);
      timer.record(5, TimeUnit.MILLISECONDS);
      summary.record(17.0);
      functionCounterSource.incrementAndGet();
      functionTimerCount.incrementAndGet();
      byte[] junk = new byte[64 * 1024];
      junk[0] = (byte) i;
      if (++i % 200 == 0) {
        System.gc(); // force a GC so jvm.gc.pause records at least one sample
      }
      Thread.sleep(2);
    }
    sample.stop();
    System.out.println("[surface] done: " + i + " iterations; waiting for a final metric export ...");
    Thread.sleep(4_000);
    System.out.println("[surface] exiting");
  }

  private BridgeSurfaceApp() {}
}
