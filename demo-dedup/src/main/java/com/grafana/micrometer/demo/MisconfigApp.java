package com.grafana.micrometer.demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.binder.jvm.JvmGcMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmMemoryMetrics;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

/**
 * The app in the worked-misconfiguration narrative (work-stream 01, task 1.2).
 *
 * <p>It stands in for a service that turned the Micrometer bridge on for one reason — it has
 * <b>custom business metrics</b> written against the Micrometer API that nothing else can collect —
 * and got the JVM duplication as an unwanted side effect, because whatever wires Micrometer (here
 * the binders, in the real world Spring Boot Actuator) brings its own binders along.
 *
 * <ul>
 *   <li>{@code orders.placed} / {@code orders.latency} — the metrics the user actually wants. Only
 *       the bridge can emit these; the agent has no idea they exist.
 *   <li>{@code jvm.memory.*} — the duplication. Emitted by the bridge under the Micrometer name
 *       <i>and</i> by the agent's runtime-telemetry under the byte-identical name, so the two are
 *       distinguishable only by instrumentation scope.
 *   <li>{@code jvm.gc.pause} — a {@code Timer}, so it drags a {@code jvm.gc.pause.max} companion
 *       along and exercises the exact-name-view trap.
 * </ul>
 *
 * <p>The whole point of the demo is that these three fates must be told apart: a config change that
 * removes the duplication by removing the bridge entirely <b>also</b> removes {@code orders.*}, and
 * looks like success from the duplication side alone.
 */
public final class MisconfigApp {

  public static void main(String[] args) throws Exception {
    long runMillis = Long.getLong("demo.run.millis", 12_000L);

    // The reason this team enabled the bridge at all.
    Counter ordersPlaced =
        Counter.builder("orders.placed")
            .description("Orders accepted by the checkout service")
            .register(Metrics.globalRegistry);
    Timer orderLatency =
        Timer.builder("orders.latency")
            .description("Time to accept an order")
            .register(Metrics.globalRegistry);

    // The side effect they did not ask for: the same JVM facts the agent already reports.
    new JvmMemoryMetrics().bindTo(Metrics.globalRegistry); // jvm.memory.* — name collision
    new JvmGcMetrics().bindTo(Metrics.globalRegistry); // jvm.gc.pause — Timer, so + .max

    System.out.println("[misconfig] generating activity for " + runMillis + "ms ...");
    long deadline = System.currentTimeMillis() + runMillis;
    long i = 0;
    while (System.currentTimeMillis() < deadline) {
      ordersPlaced.increment();
      orderLatency.record(ThreadLocalRandom.current().nextInt(1, 50), TimeUnit.MILLISECONDS);
      byte[] junk = new byte[64 * 1024];
      junk[0] = (byte) i;
      if (++i % 200 == 0) {
        System.gc(); // force a GC so jvm.gc.pause records at least one sample
      }
      Thread.sleep(2);
    }
    System.out.println("[misconfig] done: " + i + " orders; waiting for a final metric export ...");
    Thread.sleep(4_000);
    System.out.println("[misconfig] exiting");
  }

  private MisconfigApp() {}
}
