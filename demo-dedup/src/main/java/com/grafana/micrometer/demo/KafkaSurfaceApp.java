package com.grafana.micrometer.demo;

import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.binder.kafka.KafkaClientMetrics;
import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;

/**
 * Companion to {@link BridgeSurfaceApp} for the <b>second</b> half of the v2/v3-preview surface
 * delta: the agent's {@code kafka-clients-metrics} bridge is on by default today and off under
 * {@code otel.instrumentation.common.v3-preview}
 * ({@code KafkaMetricsInstrumentationModule.defaultEnabled()}).
 *
 * <p>That flip is load-bearing for this project: 115 of the 155 {@code drop(duplicate)} rows in the
 * decision table defer to that bridge, so under v3-preview their counterpart disappears and the
 * drop becomes wrong.
 *
 * <p><b>No broker is needed.</b> A {@code KafkaProducer} registers its client metrics with every
 * configured {@code MetricsReporter} during construction, and the agent injects its
 * {@code OpenTelemetryMetricsReporter} into that list. Pointing at a dead broker keeps the run
 * hermetic (no Docker) while still exercising the bridge; the producer's connection attempts fail in
 * the background and are irrelevant to metric registration.
 *
 * <p>Micrometer's own {@link KafkaClientMetrics} is bound to the global registry as well, so a
 * single run shows both sides of the duplicate pair: Micrometer's dotted {@code kafka.*} names
 * bridged under {@code io.opentelemetry.micrometer-1.5}, and the agent's underscored ones under
 * {@code io.opentelemetry.kafka-clients-0.11}.
 */
public final class KafkaSurfaceApp {

  public static void main(String[] args) throws Exception {
    long runMillis = Long.getLong("demo.run.millis", 12_000L);

    Properties props = new Properties();
    // A port nothing listens on: metric registration happens at construction, not on connect.
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "127.0.0.1:1");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
    props.put(ProducerConfig.CLIENT_ID_CONFIG, "surface-probe");
    props.put(ProducerConfig.MAX_BLOCK_MS_CONFIG, "500");
    props.put(ProducerConfig.RECONNECT_BACKOFF_MAX_MS_CONFIG, "1000");

    try (KafkaProducer<String, String> producer = new KafkaProducer<>(props);
        KafkaClientMetrics micrometerKafka = new KafkaClientMetrics(producer)) {
      micrometerKafka.bindTo(Metrics.globalRegistry);

      System.out.println("[kafka-surface] producer + Micrometer binder up; idling " + runMillis + "ms ...");
      long deadline = System.currentTimeMillis() + runMillis;
      while (System.currentTimeMillis() < deadline) {
        // A send that will never be acknowledged. It still moves the client's request/record
        // metrics off zero, which is enough for the exporter to emit them.
        producer.send(new org.apache.kafka.clients.producer.ProducerRecord<>("surface-topic", "k", "v"));
        Thread.sleep(250);
      }
      System.out.println("[kafka-surface] waiting for a final metric export ...");
      Thread.sleep(4_000);
    } catch (RuntimeException e) {
      // A dead broker makes send()/close() throw; the metrics have already been registered.
      System.out.println("[kafka-surface] expected broker failure: " + e);
      Thread.sleep(4_000);
    }
    System.out.println("[kafka-surface] exiting");
  }

  private KafkaSurfaceApp() {}
}
