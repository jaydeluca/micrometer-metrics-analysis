package com.grafana.micrometer.demo;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.binder.cache.CaffeineCacheMetrics;
import io.micrometer.core.instrument.binder.jvm.ClassLoaderMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmGcMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmMemoryMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmThreadMetrics;
import io.micrometer.core.instrument.binder.system.FileDescriptorMetrics;
import io.micrometer.core.instrument.binder.system.ProcessorMetrics;
import io.micrometer.core.instrument.binder.system.UptimeMetrics;
import java.util.concurrent.ThreadLocalRandom;

/**
 * Demo app for validating the Micrometer-dedup declarative-config views.
 *
 * <p>It binds a spread of Micrometer core binders to {@link Metrics#globalRegistry}. When this runs
 * under the OTel Java agent with {@code otel.instrumentation.micrometer.enabled=true}, the agent has
 * already added its {@code OpenTelemetryMeterRegistry} to that global composite (via advice on the
 * static initializer of {@code io.micrometer.core.instrument.Metrics}), so every meter bound here is
 * bridged to OpenTelemetry under instrumentation scope {@code io.opentelemetry.micrometer-1.5}.
 *
 * <p>The binders are chosen to exercise all three cases the views must handle:
 * <ul>
 *   <li><b>Name collision</b> — {@code jvm.memory.*}: emitted by BOTH the agent's native
 *       runtime-telemetry (a different scope) and the Micrometer bridge under the SAME name. The
 *       scope-guarded drop view must remove only the bridged copy.
 *   <li><b>Drop</b> — {@code jvm.gc.pause}, {@code jvm.classes.loaded/.unloaded},
 *       {@code jvm.threads.live}, {@code process.cpu.*}, {@code process.files.*},
 *       {@code system.*}: Micrometer names the agent covers natively.
 *   <li><b>Keep</b> — {@code cache.*} (agent has no cache binder), {@code process.uptime}, plus the
 *       Micrometer-only siblings {@code jvm.gc.memory.allocated}, {@code jvm.classes.loaded.count},
 *       {@code jvm.threads.daemon/peak/states}: no agent equivalent, must survive.
 * </ul>
 */
public final class DemoApp {

  public static void main(String[] args) throws Exception {
    long runMillis = Long.getLong("demo.run.millis", 15_000L);

    // Bind to the GLOBAL composite registry — the one the agent's bridge attaches to.
    new JvmMemoryMetrics().bindTo(Metrics.globalRegistry); // jvm.memory.* (collides with native)
    new JvmGcMetrics().bindTo(Metrics.globalRegistry); // jvm.gc.pause (drop) + jvm.gc.memory.* (keep)
    new ClassLoaderMetrics().bindTo(Metrics.globalRegistry); // jvm.classes.loaded/.unloaded (drop)
    new JvmThreadMetrics().bindTo(Metrics.globalRegistry); // jvm.threads.live (drop) + daemon/... (keep)
    new ProcessorMetrics().bindTo(Metrics.globalRegistry); // system.cpu.*, process.cpu.* (drop)
    new FileDescriptorMetrics().bindTo(Metrics.globalRegistry); // process.files.* (drop)
    new UptimeMetrics().bindTo(Metrics.globalRegistry); // process.uptime (keep — Micrometer-only)

    Cache<Integer, Integer> cache = Caffeine.newBuilder().recordStats().maximumSize(500).build();
    CaffeineCacheMetrics.monitor(Metrics.globalRegistry, cache, "demoCache"); // cache.* (keep)

    System.out.println("[demo] generating activity for " + runMillis + "ms ...");
    long deadline = System.currentTimeMillis() + runMillis;
    long i = 0;
    while (System.currentTimeMillis() < deadline) {
      int key = ThreadLocalRandom.current().nextInt(1_000);
      if (cache.getIfPresent(key) == null) {
        cache.put(key, key); // exercise cache.gets (miss) + cache.puts
      }
      byte[] junk = new byte[64 * 1024]; // allocate so the heap moves and GC eventually runs
      junk[0] = (byte) i;
      if (++i % 200 == 0) {
        System.gc(); // force a GC so jvm.gc.pause records at least one sample
      }
      Thread.sleep(2);
    }
    System.out.println("[demo] done: " + i + " iterations; waiting for a final metric export ...");
    // Let the periodic metric reader flush at least one more time before the JVM exits.
    Thread.sleep(4_000);
    System.out.println("[demo] exiting");
  }

  private DemoApp() {}
}