package com.grafana.micrometer.inventory.tier3;

import com.grafana.micrometer.inventory.capture.CaptureSession;
import com.grafana.micrometer.inventory.capture.InventoryWriter;
import com.grafana.micrometer.inventory.capture.RunMeta;
import com.grafana.micrometer.inventory.model.Inventory;
import io.micrometer.core.instrument.MeterRegistry;
import java.nio.file.Path;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

/**
 * Tier 3 harness — a real Spring Boot app. Unlike tiers 0–2 (individual binders), here a fully wired
 * Actuator context populates one {@link MeterRegistry} via autoconfiguration. We boot the app, drive
 * a little server + client + DB traffic so the request/pool meters materialize, then dump the whole
 * registry via {@link CaptureSession#captureRegistry}.
 *
 * <p>Captures the Spring-specific surface no core binder emits: {@code http.server.requests}
 * (WebMVC), {@code http.client.requests} (instrumented RestTemplate), {@code jdbc.connections.*}
 * (DataSourcePoolMetrics), plus Actuator's auto-wiring of the JVM/system/Tomcat/Logback binders.
 */
@SpringBootApplication
@RestController
public class Tier3App {

    @GetMapping("/probe")
    public String probe() {
        return "ok";
    }

    public static void main(String[] args) throws Exception {
        Path out = Path.of(System.getProperty("inventory.out", "inventory/micrometer-tier3.json"));

        ConfigurableApplicationContext ctx = new SpringApplication(Tier3App.class).run(args);
        try {
            int port = ((ServletWebServerApplicationContext) ctx).getWebServer().getPort();

            // Server + client traffic: the instrumented RestTemplate calling our own endpoint
            // exercises both http.client.requests and http.server.requests.
            RestTemplate restTemplate = ctx.getBean(RestTemplateBuilder.class).build();
            restTemplate.getForObject("http://127.0.0.1:" + port + "/probe", String.class);

            // DB traffic so the connection-pool meters (jdbc.connections.*, hikaricp.*) populate.
            ctx.getBean(JdbcTemplate.class).queryForObject("SELECT 1", Integer.class);

            // WebMVC records http.server.requests after the response completes; let it settle.
            Thread.sleep(1000);

            CaptureSession session = new CaptureSession(RunMeta.detect());
            session.captureRegistry(ctx.getBean(MeterRegistry.class), 3, "spring-boot-actuator", Tier3App::bucket);

            Inventory inventory = session.build();
            InventoryWriter writer = new InventoryWriter();
            writer.write(inventory, out);
            writer.printSummary(inventory, out);
        } finally {
            ctx.close();
        }
        System.exit(0); // embedded server threads otherwise keep the JVM alive
    }

    /** Map a metric name to the canonical comparison bucket (kept in sync with tools/compare.py). */
    static String bucket(String name) {
        if (name.startsWith("http.server.")) {
            return "http.server";
        }
        if (name.startsWith("http.client.")) {
            return "http.client";
        }
        if (name.startsWith("jdbc.") || name.startsWith("hikaricp.")) {
            return "db.pool";
        }
        if (name.startsWith("jvm.")) {
            return "jvm";
        }
        if (name.startsWith("system.") || name.startsWith("process.") || name.startsWith("disk.")) {
            return "system";
        }
        if (name.startsWith("tomcat.")) {
            return "tomcat";
        }
        if (name.startsWith("logback.") || name.startsWith("log4j2.")) {
            return "logging";
        }
        if (name.startsWith("executor.")) {
            return "executor";
        }
        if (name.startsWith("spring.") || name.startsWith("application.")) {
            return "spring";
        }
        return name.split("\\.", 2)[0];
    }
}
