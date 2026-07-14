package com.grafana.micrometer.inventory.tier2;

import com.grafana.micrometer.inventory.capture.BinderSpec;
import com.grafana.micrometer.inventory.capture.CaptureSession;
import com.grafana.micrometer.inventory.capture.InventoryWriter;
import com.grafana.micrometer.inventory.capture.RunMeta;
import com.grafana.micrometer.inventory.model.Inventory;
import io.micrometer.core.instrument.binder.grpc.MetricCollectingClientInterceptor;
import java.nio.file.Path;

/**
 * Tier 2 harness — gRPC (in-process, no Docker). Captures Micrometer's metric-collecting gRPC
 * interceptors: a single in-process unary call materializes the client + server counters and
 * processing-duration timers, which {@link CaptureSession} then reads back.
 *
 * <p>Note for the comparison: the OTel agent's gRPC metrics are the semconv {@code rpc.*}
 * (legacy {@code rpc.{client,server}.duration} / stable {@code rpc.{client,server}.call.duration}),
 * a single duration histogram per side. Micrometer instead splits each side into a request counter,
 * a response counter, and a processing-duration Timer (`grpc.*`) — mapped in {@code concept_map.yaml}.
 */
public final class GrpcMain {

    public static void main(String[] args) throws Exception {
        Path out = Path.of(System.getProperty("inventory.out", "inventory/micrometer-tier2-grpc.json"));
        CaptureSession session = new CaptureSession(RunMeta.detect());

        session.capture(BinderSpec.of("rpc", 2, GrpcMetricsBinder.class, GrpcMetricsBinder::new)
                .emittedBy(MetricCollectingClientInterceptor.class.getPackageName()
                        + ".MetricCollecting{Client,Server}Interceptor"));

        Inventory inventory = session.build();
        InventoryWriter writer = new InventoryWriter();
        writer.write(inventory, out);
        writer.printSummary(inventory, out);
    }

    private GrpcMain() {}
}
