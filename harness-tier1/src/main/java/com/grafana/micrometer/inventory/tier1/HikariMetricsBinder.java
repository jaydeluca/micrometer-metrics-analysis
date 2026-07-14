package com.grafana.micrometer.inventory.tier1;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.metrics.micrometer.MicrometerMetricsTrackerFactory;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;

/**
 * Adapts HikariCP's {@code hikaricp.connections.*} metrics to the binder-based capture model.
 *
 * <p>Unlike the JVM/cache binders, HikariCP does not ship a {@code MeterBinder}: its metrics are
 * emitted by {@link MicrometerMetricsTrackerFactory}, wired into a {@link HikariDataSource} at
 * construction. We bridge that into a synthetic {@code MeterBinder} so the capture session can drive
 * it uniformly — {@link #bindTo} builds an H2-backed pool against the supplied registry and opens
 * one connection so the gauges/timers materialize. The {@code emittedBy} attribution is corrected to
 * the tracker factory via {@code BinderSpec.emittedBy(String)}.
 *
 * <p>This is the only JDBC pool with native (non-Spring) Micrometer support. The other pools
 * (DBCP2, Tomcat JDBC, c3p0, Vibur, Druid, Oracle UCP) surface through Spring's
 * {@code DataSourcePoolMetrics} (`jdbc.connections.*`) and belong to the Spring Boot harness (Tier 3).
 */
final class HikariMetricsBinder implements MeterBinder, AutoCloseable {

    private HikariDataSource dataSource;

    @Override
    public void bindTo(MeterRegistry registry) {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:h2:mem:tier1-hikari;DB_CLOSE_DELAY=-1");
        config.setUsername("sa");
        config.setPassword("");
        config.setPoolName("tier1-hikari");
        config.setMaximumPoolSize(2);
        config.setMinimumIdle(1);
        config.setMetricsTrackerFactory(new MicrometerMetricsTrackerFactory(registry));
        dataSource = new HikariDataSource(config);
        // One connection materializes the usage/acquire timers and the pool-state gauges.
        try (Connection connection = dataSource.getConnection();
                Statement statement = connection.createStatement()) {
            statement.execute("SELECT 1");
        } catch (SQLException e) {
            throw new IllegalStateException("failed to exercise HikariCP pool", e);
        }
    }

    @Override
    public void close() {
        if (dataSource != null) {
            dataSource.close();
        }
    }
}
