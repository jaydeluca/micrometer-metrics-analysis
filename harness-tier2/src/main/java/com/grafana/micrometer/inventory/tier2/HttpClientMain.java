package com.grafana.micrometer.inventory.tier2;

import com.grafana.micrometer.inventory.capture.BinderSpec;
import com.grafana.micrometer.inventory.capture.CaptureSession;
import com.grafana.micrometer.inventory.capture.InventoryWriter;
import com.grafana.micrometer.inventory.capture.RunMeta;
import com.grafana.micrometer.inventory.model.Inventory;
import com.sun.net.httpserver.HttpServer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;
import io.micrometer.core.instrument.binder.httpcomponents.hc5.MicrometerHttpRequestExecutor;
import io.micrometer.core.instrument.binder.okhttp3.OkHttpMetricsEventListener;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import org.apache.hc.client5.http.classic.methods.HttpGet;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClientBuilder;
import org.apache.hc.core5.http.io.entity.EntityUtils;

/**
 * Tier 2 harness — HTTP clients (in-process, no Docker). Drives OkHttp and Apache HttpClient 5
 * against a tiny JDK {@link HttpServer} stub so their Micrometer request-timing metrics
 * ({@code okhttp.requests}, {@code httpcomponents.httpclient.request}) materialize, then reads them
 * back. These are the Micrometer counterpart to the agent's {@code http.client.request.duration}.
 *
 * <p>Like the gRPC/Kafka/Hikari cases, these aren't {@code MeterBinder}s — OkHttp uses an
 * {@code EventListener}, HC5 a custom {@code HttpRequestExecutor} — so each is wrapped in a
 * synthetic binder whose {@code bindTo} builds the client against the capture registry and makes one
 * request.
 */
public final class HttpClientMain {

    public static void main(String[] args) throws Exception {
        Path out = Path.of(System.getProperty("inventory.out", "inventory/micrometer-tier2-httpclient.json"));
        CaptureSession session = new CaptureSession(RunMeta.detect());

        HttpServer stub = startStub();
        String baseUrl = "http://127.0.0.1:" + stub.getAddress().getPort() + "/probe";
        try {
            session.capture(BinderSpec.of("http.client", 2, OkHttpRequestBinder.class,
                            () -> new OkHttpRequestBinder(baseUrl))
                    .emittedBy("io.micrometer.core.instrument.binder.okhttp3.OkHttpMetricsEventListener"));
            session.capture(BinderSpec.of("http.client", 2, ApacheHc5RequestBinder.class,
                            () -> new ApacheHc5RequestBinder(baseUrl))
                    .emittedBy("io.micrometer.core.instrument.binder.httpcomponents.hc5.MicrometerHttpRequestExecutor"));
        } finally {
            stub.stop(0);
        }

        Inventory inventory = session.build();
        InventoryWriter writer = new InventoryWriter();
        writer.write(inventory, out);
        writer.printSummary(inventory, out);
    }

    private static HttpServer startStub() throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(body);
            }
        });
        server.start();
        return server;
    }

    /** OkHttp client wired with {@link OkHttpMetricsEventListener}; one GET → {@code okhttp.requests}. */
    private static final class OkHttpRequestBinder implements MeterBinder, AutoCloseable {
        private final String url;
        private OkHttpClient client;

        OkHttpRequestBinder(String url) {
            this.url = url;
        }

        @Override
        public void bindTo(MeterRegistry registry) {
            client = new OkHttpClient.Builder()
                    .eventListener(OkHttpMetricsEventListener.builder(registry, "okhttp.requests").build())
                    .build();
            try (Response response = client.newCall(new Request.Builder().url(url).build()).execute()) {
                if (response.body() != null) {
                    response.body().string(); // consume so the call (and its timer) completes
                }
            } catch (IOException e) {
                throw new IllegalStateException("OkHttp probe failed", e);
            }
        }

        @Override
        public void close() {
            if (client != null) {
                client.dispatcher().executorService().shutdown();
                client.connectionPool().evictAll();
            }
        }
    }

    /** Apache HC5 client wired with {@link MicrometerHttpRequestExecutor}; one GET → the request timer. */
    private static final class ApacheHc5RequestBinder implements MeterBinder, AutoCloseable {
        private final String url;
        private CloseableHttpClient client;

        ApacheHc5RequestBinder(String url) {
            this.url = url;
        }

        @Override
        public void bindTo(MeterRegistry registry) {
            client = HttpClientBuilder.create()
                    .setRequestExecutor(MicrometerHttpRequestExecutor.builder(registry).build())
                    .build();
            try {
                client.execute(new HttpGet(url), response -> {
                    EntityUtils.consume(response.getEntity());
                    return null;
                });
            } catch (IOException e) {
                throw new IllegalStateException("Apache HC5 probe failed", e);
            }
        }

        @Override
        public void close() {
            if (client != null) {
                try {
                    client.close();
                } catch (IOException ignored) {
                    // best-effort
                }
            }
        }
    }

    private HttpClientMain() {}
}
