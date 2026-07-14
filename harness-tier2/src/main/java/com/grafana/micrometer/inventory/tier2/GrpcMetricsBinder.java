package com.grafana.micrometer.inventory.tier2;

import io.grpc.CallOptions;
import io.grpc.ManagedChannel;
import io.grpc.MethodDescriptor;
import io.grpc.Server;
import io.grpc.ServerServiceDefinition;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.ClientCalls;
import io.grpc.stub.ServerCalls;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;
import io.micrometer.core.instrument.binder.grpc.MetricCollectingClientInterceptor;
import io.micrometer.core.instrument.binder.grpc.MetricCollectingServerInterceptor;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

/**
 * Adapts Micrometer's gRPC metrics to the binder-based capture model.
 *
 * <p>gRPC metrics are emitted by {@link MetricCollectingClientInterceptor} /
 * {@link MetricCollectingServerInterceptor} (a {@code ClientInterceptor}/{@code ServerInterceptor}),
 * not a {@code MeterBinder}, and the per-method counters/timers are created lazily on the first
 * call. So {@link #bindTo} stands up a fully in-process gRPC round trip — a server and channel both
 * wired with the interceptors bound to the capture registry — and makes one unary call, after which
 * all six {@code grpc.{client,server}.*} meters exist. No network, no Docker.
 *
 * <p>A hand-rolled {@code String}-marshalled unary method avoids any protobuf code generation.
 */
final class GrpcMetricsBinder implements MeterBinder, AutoCloseable {

    private static final MethodDescriptor.Marshaller<String> STRING_MARSHALLER =
            new MethodDescriptor.Marshaller<>() {
                @Override
                public InputStream stream(String value) {
                    return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8));
                }

                @Override
                public String parse(InputStream stream) {
                    try {
                        return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                }
            };

    private static final MethodDescriptor<String, String> ECHO = MethodDescriptor.<String, String>newBuilder()
            .setType(MethodDescriptor.MethodType.UNARY)
            .setFullMethodName(MethodDescriptor.generateFullMethodName("tier2.Echo", "Echo"))
            .setRequestMarshaller(STRING_MARSHALLER)
            .setResponseMarshaller(STRING_MARSHALLER)
            .build();

    private Server server;
    private ManagedChannel channel;

    @Override
    public void bindTo(MeterRegistry registry) {
        String name = "tier2-grpc-" + System.identityHashCode(this);
        ServerServiceDefinition service = ServerServiceDefinition.builder("tier2.Echo")
                .addMethod(ECHO, ServerCalls.asyncUnaryCall((request, responseObserver) -> {
                    responseObserver.onNext(request);
                    responseObserver.onCompleted();
                }))
                .build();
        try {
            server = InProcessServerBuilder.forName(name)
                    .directExecutor()
                    .addService(service)
                    .intercept(new MetricCollectingServerInterceptor(registry))
                    .build()
                    .start();
        } catch (IOException e) {
            throw new UncheckedIOException("failed to start in-process gRPC server", e);
        }
        channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .intercept(new MetricCollectingClientInterceptor(registry))
                .build();
        // One unary call materializes the client + server counters and processing-duration timers.
        ClientCalls.blockingUnaryCall(channel, ECHO, CallOptions.DEFAULT, "ping");
    }

    @Override
    public void close() {
        if (channel != null) {
            channel.shutdownNow();
        }
        if (server != null) {
            server.shutdownNow();
        }
    }
}
