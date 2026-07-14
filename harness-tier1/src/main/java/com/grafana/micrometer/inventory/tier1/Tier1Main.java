package com.grafana.micrometer.inventory.tier1;

import com.github.benmanes.caffeine.cache.Caffeine;
import com.google.common.cache.CacheBuilder;
import com.grafana.micrometer.inventory.capture.BinderSpec;
import com.grafana.micrometer.inventory.capture.CaptureSession;
import com.grafana.micrometer.inventory.capture.InventoryWriter;
import com.grafana.micrometer.inventory.capture.RunMeta;
import com.grafana.micrometer.inventory.model.Inventory;
import io.micrometer.core.instrument.binder.cache.CaffeineCacheMetrics;
import io.micrometer.core.instrument.binder.cache.GuavaCacheMetrics;
import io.micrometer.core.instrument.binder.commonspool2.CommonsObjectPool2Metrics;
import io.micrometer.core.instrument.binder.netty4.NettyAllocatorMetrics;
import io.micrometer.core.instrument.binder.netty4.NettyEventExecutorMetrics;
import io.micrometer.core.instrument.binder.okhttp3.OkHttpConnectionPoolMetrics;
import io.netty.buffer.ByteBuf;
import io.netty.buffer.PooledByteBufAllocator;
import io.netty.channel.nio.NioEventLoopGroup;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.apache.commons.pool2.BasePooledObjectFactory;
import org.apache.commons.pool2.PooledObject;
import org.apache.commons.pool2.impl.DefaultPooledObject;
import org.apache.commons.pool2.impl.GenericObjectPool;

/**
 * Tier 1 harness: in-process library objects, no Docker, no Spring. Each binder is constructed
 * against a real (in-memory / local) target and exercised just enough to materialize its meters,
 * then read back by {@link CaptureSession}.
 *
 * <p>Buckets captured here: {@code cache} (Caffeine, Guava — the cache metric surface is shared
 * across all {@code CacheMeterBinder}s), {@code pool} (Commons Pool 2), {@code netty} (allocator +
 * event executor), {@code http.client} (OkHttp connection pool), and {@code db.pool} (HikariCP via
 * {@link HikariMetricsBinder}). Only the {@code micrometer} convention is captured — Tier 0
 * established the OTLP export naming is identity.
 */
public final class Tier1Main {

    public static void main(String[] args) throws Exception {
        Path out = Path.of(System.getProperty("inventory.out", "inventory/micrometer-tier1.json"));
        CaptureSession session = new CaptureSession(RunMeta.detect());

        // Long-lived targets: created once, shared by factory + activity, shut down after capture.
        NioEventLoopGroup eventLoopGroup = new NioEventLoopGroup(1);
        GenericObjectPool<Object> objectPool = new GenericObjectPool<>(new TrivialPooledObjectFactory());

        try {
            for (BinderSpec spec : specs(eventLoopGroup, objectPool)) {
                session.capture(spec);
            }
        } finally {
            objectPool.close();
            eventLoopGroup.shutdownGracefully();
        }

        Inventory inventory = session.build();
        InventoryWriter writer = new InventoryWriter();
        writer.write(inventory, out);
        writer.printSummary(inventory, out);
    }

    private static List<BinderSpec> specs(NioEventLoopGroup eventLoopGroup, GenericObjectPool<Object> objectPool) {
        List<BinderSpec> specs = new ArrayList<>();
        int tier = 1;

        // ---- caches: drive one put + hit + miss so gets/puts/evictions/load meters exist ----
        com.github.benmanes.caffeine.cache.Cache<String, String> caffeine =
                Caffeine.newBuilder().recordStats().maximumSize(10).build();
        specs.add(BinderSpec.of(
                        "cache", tier, CaffeineCacheMetrics.class,
                        () -> new CaffeineCacheMetrics<>(caffeine, "tier1-caffeine", List.of()))
                .withActivity(reg -> {
                    caffeine.put("k", "v");
                    caffeine.getIfPresent("k");   // hit
                    caffeine.getIfPresent("miss"); // miss
                }));

        com.google.common.cache.Cache<String, String> guava =
                CacheBuilder.newBuilder().recordStats().maximumSize(10).build();
        specs.add(BinderSpec.of(
                        "cache", tier, GuavaCacheMetrics.class,
                        () -> new GuavaCacheMetrics<>(guava, "tier1-guava", List.of()))
                .withActivity(reg -> {
                    guava.put("k", "v");
                    guava.getIfPresent("k");
                    guava.getIfPresent("miss");
                }));

        // ---- Commons Pool 2: the binder reads JMX MBeans; the pool must exist + be exercised ----
        specs.add(BinderSpec.of("pool", tier, CommonsObjectPool2Metrics.class, CommonsObjectPool2Metrics::new)
                .withActivity(reg -> borrowReturn(objectPool)));

        // ---- Netty 4: allocator (allocate one buffer) + event-executor group ----
        specs.add(BinderSpec.of(
                        "netty", tier, NettyAllocatorMetrics.class,
                        () -> new NettyAllocatorMetrics(PooledByteBufAllocator.DEFAULT))
                .withActivity(reg -> {
                    ByteBuf buf = PooledByteBufAllocator.DEFAULT.buffer(256);
                    buf.release();
                }));
        specs.add(BinderSpec.of(
                "netty", tier, NettyEventExecutorMetrics.class,
                () -> new NettyEventExecutorMetrics(eventLoopGroup)));

        // ---- OkHttp connection pool: gauges read pool state at bind time, no traffic needed ----
        specs.add(BinderSpec.of(
                "http.client", tier, OkHttpConnectionPoolMetrics.class,
                () -> new OkHttpConnectionPoolMetrics(new okhttp3.ConnectionPool())));

        // ---- HikariCP: native hikaricp.connections.* via the tracker factory (H2-backed) ----
        specs.add(BinderSpec.of("db.pool", tier, HikariMetricsBinder.class, HikariMetricsBinder::new)
                .emittedBy("com.zaxxer.hikari.metrics.micrometer.MicrometerMetricsTrackerFactory"));

        return specs;
    }

    private static void borrowReturn(GenericObjectPool<Object> pool) {
        try {
            Object o = pool.borrowObject();
            pool.returnObject(o);
        } catch (Exception ignored) {
            // a missing borrow just means fewer populated gauges; not fatal to the inventory
        }
    }

    /** Minimal factory so a {@link GenericObjectPool} can be created and exercised. */
    private static final class TrivialPooledObjectFactory extends BasePooledObjectFactory<Object> {
        @Override
        public Object create() {
            return new Object();
        }

        @Override
        public PooledObject<Object> wrap(Object obj) {
            return new DefaultPooledObject<>(obj);
        }
    }

    private Tier1Main() {}
}
