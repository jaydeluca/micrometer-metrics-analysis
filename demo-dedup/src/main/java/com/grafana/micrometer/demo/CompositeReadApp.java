package com.grafana.micrometer.demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.util.List;

/**
 * Does suppressing a meter inside the bridge corrupt reads through the composite?
 *
 * <p>This is the acceptance test for the Layer A vs Layer B question in the metric-bridge-interop
 * project. Both layers stop a metric being exported; they differ in what object they leave in the
 * composite's per-registry child map, and {@code AbstractCompositeMeter#firstChild()} answers reads
 * from whichever child it happens to iterate first.
 *
 * <p>The agent rewrites {@code firstChild()} to skip children implementing {@code
 * OpenTelemetryInstrument}. So:
 *
 * <ul>
 *   <li>a suppressed meter carrying that marker (Layer B) should be skipped, and the read should be
 *       answered by the sibling {@link SimpleMeterRegistry} that can actually report values;
 *   <li>a plain Micrometer noop -- what a {@code MeterFilter} DENY leaves behind, i.e. Layer A --
 *       carries no marker, so the read can be answered from it and return 0.
 * </ul>
 *
 * <p>Run under the agent with the Micrometer bridge on. Pass {@code
 * -Dotel.javaagent.micrometer.spike.unmarked-suppression=true} for the Layer A artifact.
 *
 * <p>Every name below is in the spike's suppression set except the control. They are registered as
 * plain counters: the predicate is keyed on the metric name, so what binder would normally produce
 * them is irrelevant to this probe.
 */
public final class CompositeReadApp {

  private static final String CONTROL = "demo.control.counter";
  private static final String SUPPRESSED_TIMER = "http.server.requests";
  private static final List<String> SUPPRESSED =
      List.of(
          "jvm.classes.unloaded", "jvm.memory.used", "system.cpu.count", "process.files.open");

  public static void main(String[] args) throws Exception {
    // Touching Metrics runs its static initializer, which is where the agent adds its bridge
    // registry to the global composite. The sibling is therefore always added second -- which is
    // also the real ordering in a Spring Boot app, where Actuator's registry is created by the
    // application context long after the agent has attached.
    SimpleMeterRegistry sibling = new SimpleMeterRegistry();
    Metrics.addRegistry(sibling);

    CompositeMeterRegistry composite = Metrics.globalRegistry;
    List<MeterRegistry> children = List.copyOf(composite.getRegistries());
    System.out.println("PROBE registries=" + children.size());
    for (MeterRegistry registry : children) {
      System.out.println("PROBE registry " + registry.getClass().getName());
    }
    // Which arm of the spike lever is live. Printed rather than inferred: a read that comes back
    // correct proves nothing on its own unless we know whether the marker was actually suppressed.
    System.out.println(
        "PROBE unmarked-lever="
            + System.getProperty("otel.javaagent.micrometer.spike.unmarked-suppression", "unset"));

    check(CONTROL, 5);
    for (String name : SUPPRESSED) {
      check(name, 5);
    }

    // A Timer in the suppression set. Under `all` the bridge emits it plus an `http.server.requests.max`
    // companion gauge; suppressing at registration should take both, since the companion is created
    // inside OpenTelemetryTimer and that object is never constructed. This is the orphan an
    // exact-name SDK view leaves behind.
    Timer timer = Metrics.timer(SUPPRESSED_TIMER);
    for (int i = 0; i < 5; i++) {
      timer.record(Duration.ofMillis(10));
    }

    // Let one export cycle run so the OTLP capture is comparable with the other harnesses.
    Thread.sleep(Long.getLong("demo.run.millis", 8000L));
    System.out.println("PROBE done");
  }

  private static void check(String name, int increments) {
    Counter counter = Metrics.counter(name);
    for (int i = 0; i < increments; i++) {
      counter.increment();
    }

    // Reads the composite, which delegates to firstChild(). This is the path Actuator's
    // /actuator/metrics endpoint takes.
    Meter found = Metrics.globalRegistry.find(name).meter();
    double readBack = found == null ? Double.NaN : Metrics.globalRegistry.get(name).counter().count();

    System.out.println(
        "PROBE read name=" + name + " expected=" + increments + " got=" + readBack);

    // The per-child objects behind that read, in composite iteration order. This is what decides the
    // answer: firstChild() takes the first child the agent's rewrite does not skip. Printing the
    // classes distinguishes "the marker worked" from "the bridge child was never a noop at all".
    StringBuilder childClasses = new StringBuilder();
    for (MeterRegistry registry : Metrics.globalRegistry.getRegistries()) {
      Meter child = registry.find(name).meter();
      childClasses
          .append(childClasses.length() == 0 ? "" : ",")
          .append(child == null ? "absent" : child.getClass().getSimpleName());
    }
    System.out.println("PROBE children name=" + name + " classes=" + childClasses);
  }

  private CompositeReadApp() {}
}
