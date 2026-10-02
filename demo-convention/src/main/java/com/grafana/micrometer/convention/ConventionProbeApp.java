package com.grafana.micrometer.convention;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Configuration;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.jvm.convention.JvmClassLoadingMeterConventions;
import io.micrometer.core.instrument.binder.jvm.convention.JvmCpuMeterConventions;
import io.micrometer.core.instrument.binder.jvm.convention.JvmMemoryMeterConventions;
import io.micrometer.core.instrument.binder.jvm.convention.JvmThreadMeterConventions;
import io.micrometer.core.instrument.binder.jvm.convention.otel.OpenTelemetryJvmClassLoadingMeterConventions;
import io.micrometer.core.instrument.binder.jvm.convention.otel.OpenTelemetryJvmCpuMeterConventions;
import io.micrometer.core.instrument.binder.jvm.convention.otel.OpenTelemetryJvmMemoryMeterConventions;
import io.micrometer.core.instrument.binder.jvm.convention.otel.OpenTelemetryJvmThreadMeterConventions;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.http.server.observation.DefaultServerRequestObservationConvention;
import org.springframework.http.server.observation.OpenTelemetryServerRequestObservationConvention;
import org.springframework.http.server.observation.ServerRequestObservationConvention;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

/**
 * A real Spring Boot app under the real agent, run twice, to answer stage-02 item A3's sharpened
 * question: <b>does opting into Spring's semconv-named observation convention defeat a drop-set
 * keyed on Micrometer's historical metric name?</b>
 *
 * <p>The two runs differ only in which {@link ServerRequestObservationConvention} bean is present:
 *
 * <ul>
 *   <li>{@code -Dprobe.convention=default} — {@link DefaultServerRequestObservationConvention},
 *       Boot's default. The meter is named {@code http.server.requests}.
 *   <li>{@code -Dprobe.convention=otel} — {@link OpenTelemetryServerRequestObservationConvention}
 *       ({@code spring-web}, {@code @since 7.0}). The meter is named {@code
 *       http.server.request.duration} — the same name the agent's own HTTP instrumentation emits.
 * </ul>
 *
 * <p>Why this is the load-bearing case rather than a curiosity: the drop-set in {@code
 * inventory/decisions-v2.31.1.json} is keyed on the <i>Micrometer</i> name, which is what disposes
 * of FM-4 conditionality (a {@code hikaricp.*} meter cannot exist in an app without HikariCP). It
 * holds a {@code drop(duplicate)} row for {@code http.server.requests} and <b>no row at all</b> for
 * {@code http.server.request.duration}. Opting into the convention above therefore changes the key
 * the policy looks up, and it is opt-in <i>by user-authored bean</i> — invisible to every agent
 * property, so the bridge cannot detect it from configuration.
 *
 * <p>Both runs also emit the agent's native {@code http.server.request.duration} from
 * {@code spring-webmvc}/{@code servlet}, so the capture shows the collision shape directly: same
 * name, and whatever the bridge does to unit, instrument type, and attribute keys.
 *
 * <p>Traffic is driven with the JDK {@link HttpClient} on purpose — Micrometer does not instrument
 * it, so nothing here adds a competing {@code http.client.requests} series to the capture.
 */
@SpringBootApplication
public class ConventionProbeApp {

  /** Route with a path variable, so {@code http.route} is a template rather than a literal path. */
  @RestController
  static class ProbeController {
    @GetMapping("/probe/{id}")
    String probe(@PathVariable("id") String id) {
      return "ok:" + id;
    }
  }

  /**
   * The single difference between the two runs. Boot picks this up via {@code
   * ObjectProvider.getIfAvailable()} in its WebMvc observation autoconfiguration — there is no
   * property that selects it, which is the finding this probe exists to make concrete.
   */
  @Bean
  ServerRequestObservationConvention serverRequestObservationConvention() {
    String which = System.getProperty("probe.convention", "default");
    if ("otel".equals(which)) {
      System.out.println(">> probe: using OpenTelemetryServerRequestObservationConvention");
      return new OpenTelemetryServerRequestObservationConvention();
    }
    System.out.println(">> probe: using DefaultServerRequestObservationConvention");
    return new DefaultServerRequestObservationConvention();
  }

  /**
   * The JVM/CPU half, added 2026-08-25. Spring Boot 4.1.1 wires exactly these four Micrometer
   * {@code MeterConvention} interfaces through {@code ObjectProvider} — {@code
   * JvmMetricsAutoConfiguration} and {@code SystemMetricsAutoConfiguration} in
   * {@code spring-boot-micrometer-metrics} — so micrometer-core's {@code convention/otel/*} classes
   * became reachable from Boot, which they were not in the November 2025 source this project's
   * earlier A3 pass read. Same bean-level opt-in as above: no property selects it.
   *
   * <p>This half matters more than the HTTP half. The bridge normalizes {@code Timer} output to its
   * own base time unit, so the HTTP collision agrees on unit — but {@code ProcessorMetrics} builds a
   * {@code FunctionCounter} with a hardcoded {@code baseUnit("ns")}, and {@code Bridging.baseUnit()}
   * passes a {@code FunctionCounter}'s unit through verbatim. So the semconv name {@code
   * jvm.cpu.time} arrives carrying nanoseconds while the agent's own {@code jvm.cpu.time} carries
   * seconds.
   */
  @Configuration
  @ConditionalOnProperty(name = "probe.jvm.convention", havingValue = "otel")
  static class OtelJvmConventions {
    @Bean
    JvmCpuMeterConventions jvmCpuMeterConventions() {
      return new OpenTelemetryJvmCpuMeterConventions(Tags.empty());
    }

    @Bean
    JvmMemoryMeterConventions jvmMemoryMeterConventions() {
      return new OpenTelemetryJvmMemoryMeterConventions(Tags.empty());
    }

    @Bean
    JvmThreadMeterConventions jvmThreadMeterConventions() {
      return new OpenTelemetryJvmThreadMeterConventions(Tags.empty());
    }

    @Bean
    JvmClassLoadingMeterConventions jvmClassLoadingMeterConventions() {
      return new OpenTelemetryJvmClassLoadingMeterConventions();
    }
  }

  public static void main(String[] args) {
    int port = Integer.getInteger("probe.port", 18080);
    int requests = Integer.getInteger("probe.requests", 20);
    long runMillis = Long.getLong("demo.run.millis", 12_000L);

    System.setProperty("server.port", Integer.toString(port));
    // Keep the surface small and predictable: no actuator endpoints exposed, no extra web traffic.
    System.setProperty("management.endpoints.web.exposure.include", "");

    // Tomcat's threads are non-daemon, so anything thrown out of here would leave the JVM alive
    // and the run script waiting forever. Always exit explicitly.
    int status = 0;
    ConfigurableApplicationContext context = null;
    try {
      context = SpringApplication.run(ConventionProbeApp.class, args);
      driveTraffic(port, requests);
      // Outlive at least one periodic export interval.
      Thread.sleep(runMillis);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      status = 1;
    } catch (Exception e) {
      e.printStackTrace();
      status = 1;
    } finally {
      if (context != null) {
        try {
          context.close();
        } catch (RuntimeException e) {
          e.printStackTrace();
        }
      }
    }
    System.exit(status);
  }

  private static void driveTraffic(int port, int requests) throws Exception {
    HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    for (int i = 0; i < requests; i++) {
      HttpRequest request =
          HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/probe/" + i))
              .timeout(Duration.ofSeconds(5))
              .GET()
              .build();
      HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
      if (response.statusCode() != 200) {
        // A 500 here means the request never reached the handler, so the observation carries the
        // error path rather than the route — the probe would measure the wrong thing.
        throw new IllegalStateException(
            "request " + i + " returned " + response.statusCode() + ": " + response.body());
      }
    }
    System.out.println(">> probe: drove " + requests + " requests against /probe/{id}");
  }
}
