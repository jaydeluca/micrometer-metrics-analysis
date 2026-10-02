package com.grafana.micrometer.demo;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.metrics.micrometer.MicrometerMetricsTrackerFactory;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.Timer;
import java.sql.Connection;
import java.sql.Statement;
import java.time.Duration;

/**
 * Enablement is not application — the two probes behind stage 04's second decision.
 *
 * <p>{@code prefer-instrumentation} decides "the agent already emits this" from two inputs: the
 * semantic-convention gate, and whether the instrumentation is enabled. Neither is the same as the
 * instrumentation having actually been <em>applied</em> to this application's classes.
 *
 * <p><b>Probe 1 — the declared muzzle range.</b> The agent's {@code hikaricp-3.0} module declares
 * {@code versions.set("[3.0.0,)")}, and HikariCP has shipped a Micrometer metrics tracker since 2.7,
 * so 2.7.9 looks like the textbook window: library present, module enabled, version below the floor.
 * Run with each HikariCP on the class path and compare. What the declared range says and what muzzle
 * enforces are two different things, and this measures the difference rather than assuming it.
 *
 * <p><b>Probe 2 — a name with no library behind it.</b> The timer registered below is named exactly
 * as the agent names its own HTTP client duration metric, which is what happens when a user opts
 * into Micrometer's or Spring's OpenTelemetry naming conventions. This application contains no HTTP
 * client library at all, so no agent instrumentation can be emitting a counterpart — but 37 HTTP
 * client instrumentations are <em>enabled</em>, and enablement is all the resolver's second,
 * name-symmetric rule has to go on. Unlike a Micrometer name, a semantic-convention name carries no
 * evidence that the library is present.
 *
 * <p>Both need {@code otel.semconv-stability.opt-in=database} for probe 1: the agent's pool metrics
 * are gated on it, so without it the resolver correctly withholds the drop and nothing happens.
 */
public final class MuzzleWindowApp {

  public static void main(String[] args) throws Exception {
    long runMillis = Long.getLong("demo.run.millis", 15_000L);

    // Report what actually loaded, rather than what the launcher intended to put on the classpath.
    Package hikari = HikariDataSource.class.getPackage();
    String version = hikari == null ? null : hikari.getImplementationVersion();
    System.out.println("PROBE hikaricp.version=" + version);

    // Rule 2's exposure, in its purest form. This meter is named exactly as the agent names its own
    // HTTP client duration metric -- which is what happens when a user opts into Micrometer's or
    // Spring's OpenTelemetry naming conventions. There is no HTTP client library anywhere in this
    // application, so no agent instrumentation can possibly be emitting it; but 37 HTTP client
    // instrumentations are *enabled*, which is all the resolver can see.
    Timer.builder("http.client.request.duration")
        .description("a user metric that collides with an agent name, with no HTTP client present")
        .register(Metrics.globalRegistry)
        .record(Duration.ofMillis(5));

    HikariConfig config = new HikariConfig();
    config.setJdbcUrl("jdbc:h2:mem:muzzlewindow;DB_CLOSE_DELAY=-1");
    config.setUsername("sa");
    config.setPassword("");
    config.setPoolName("muzzle-window-pool");
    config.setMaximumPoolSize(4);
    config.setMinimumIdle(1);
    // The user-side Micrometer copy. The agent's HikariPoolInstrumentation wraps whatever factory
    // is set here rather than replacing it, so above the floor BOTH copies are produced.
    config.setMetricsTrackerFactory(new MicrometerMetricsTrackerFactory(Metrics.globalRegistry));

    try (HikariDataSource dataSource = new HikariDataSource(config)) {
      System.out.println("[demo] exercising the pool for " + runMillis + "ms ...");
      long deadline = System.currentTimeMillis() + runMillis;
      long acquisitions = 0;
      while (System.currentTimeMillis() < deadline) {
        try (Connection connection = dataSource.getConnection();
            Statement statement = connection.createStatement()) {
          statement.execute("select 1");
          acquisitions++;
        }
        Thread.sleep(25);
      }
      System.out.println("PROBE connections.acquired=" + acquisitions);

      // Give the periodic metric reader a final collection with the pool still open.
      Thread.sleep(2_000);
    }
  }

  private MuzzleWindowApp() {}
}
