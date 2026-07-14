package com.grafana.micrometer.inventory.tier2;

import com.grafana.micrometer.inventory.capture.BinderSpec;
import com.grafana.micrometer.inventory.capture.CaptureSession;
import com.grafana.micrometer.inventory.capture.InventoryWriter;
import com.grafana.micrometer.inventory.capture.RunMeta;
import com.grafana.micrometer.inventory.model.Inventory;
import io.micrometer.core.instrument.binder.kafka.KafkaClientMetrics;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

/**
 * Tier 2 harness (Testcontainers): real dependencies driven with minimal traffic.
 *
 * <p>This first slice covers <b>Kafka</b> — the highest-value Tier 2 target because the
 * {@code kafka.*} metric names are <em>dynamic</em>: {@link KafkaClientMetrics} re-exposes the
 * client's own {@code metrics()} map (strip {@code -metrics}, {@code -}→{@code .}), so there is no
 * static list. The only way to enumerate them is to run a real client. We start a KRaft broker,
 * produce + consume + admin against it to populate each client's {@code metrics()}, then bind a
 * {@link KafkaClientMetrics} per client and read the meters back.
 *
 * <p>Ordering matters: {@code KafkaMetrics.bindTo} binds whatever {@code metrics()} holds at bind
 * time (then refreshes on a scheduler). So each client is exercised <em>before</em> its binder is
 * constructed/bound — done here by warming the clients up front and having the factory just wrap
 * the warmed client.
 *
 * <p>Note for the comparison: the OTel registry lists <em>no</em> {@code kafka.*} metrics (the
 * agent's Kafka instrumentations emit spans only; their metrics come from bridging this same
 * {@code KafkaMetrics} reporter dynamically). So these surface as a Micrometer-only bucket in the
 * registry-derived comparison, with that bridge noted.
 */
public final class KafkaMain {

    private static final String TOPIC = "tier2-topic";

    public static void main(String[] args) throws Exception {
        java.nio.file.Path out =
                java.nio.file.Path.of(System.getProperty("inventory.out", "inventory/micrometer-tier2-kafka.json"));
        CaptureSession session = new CaptureSession(RunMeta.detect());

        try (KafkaContainer kafka = new KafkaContainer(DockerImageName.parse("apache/kafka:3.8.1"))) {
            kafka.start();
            String bootstrap = kafka.getBootstrapServers();

            AdminClient admin = AdminClient.create(adminProps(bootstrap));
            Producer<String, String> producer = new KafkaProducer<>(producerProps(bootstrap));
            Consumer<String, String> consumer = new KafkaConsumer<>(consumerProps(bootstrap));
            try {
                warmUp(admin, producer, consumer);

                List<BinderSpec> specs = List.of(
                        BinderSpec.of("kafka", 2, KafkaClientMetrics.class, () -> new KafkaClientMetrics(producer))
                                .emittedBy("io.micrometer.core.instrument.binder.kafka.KafkaClientMetrics[producer]"),
                        BinderSpec.of("kafka", 2, KafkaClientMetrics.class, () -> new KafkaClientMetrics(consumer))
                                .emittedBy("io.micrometer.core.instrument.binder.kafka.KafkaClientMetrics[consumer]"),
                        BinderSpec.of("kafka", 2, KafkaClientMetrics.class, () -> new KafkaClientMetrics(admin))
                                .emittedBy("io.micrometer.core.instrument.binder.kafka.KafkaClientMetrics[admin]"));
                for (BinderSpec spec : specs) {
                    session.capture(spec);
                }
            } finally {
                consumer.close();
                producer.close();
                admin.close();
            }
        }

        Inventory inventory = session.build();
        InventoryWriter writer = new InventoryWriter();
        writer.write(inventory, out);
        writer.printSummary(inventory, out);
    }

    /** Create the topic, send a batch, and consume it so producer/consumer/admin metrics populate. */
    private static void warmUp(AdminClient admin, Producer<String, String> producer, Consumer<String, String> consumer)
            throws Exception {
        admin.createTopics(List.of(new NewTopic(TOPIC, 1, (short) 1))).all().get();
        admin.listTopics().names().get();

        for (int i = 0; i < 20; i++) {
            producer.send(new ProducerRecord<>(TOPIC, "k" + i, "v" + i));
        }
        producer.flush();

        consumer.subscribe(List.of(TOPIC));
        long deadline = System.nanoTime() + Duration.ofSeconds(15).toNanos();
        int consumed = 0;
        while (consumed < 20 && System.nanoTime() < deadline) {
            ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(500));
            consumed += records.count();
        }
        consumer.commitSync();
        System.out.printf("kafka warm-up: produced 20, consumed %d%n", consumed);
    }

    private static Properties producerProps(String bootstrap) {
        Properties p = baseProps(bootstrap);
        p.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        p.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        return p;
    }

    private static Properties consumerProps(String bootstrap) {
        Properties p = baseProps(bootstrap);
        p.put(ConsumerConfig.GROUP_ID_CONFIG, "tier2-group");
        p.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        p.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        p.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        return p;
    }

    private static Properties adminProps(String bootstrap) {
        Properties p = new Properties();
        p.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrap);
        return p;
    }

    private static Properties baseProps(String bootstrap) {
        Properties p = new Properties();
        Map<String, Object> m = new HashMap<>();
        m.put("bootstrap.servers", bootstrap);
        p.putAll(m);
        return p;
    }

    private KafkaMain() {}
}
