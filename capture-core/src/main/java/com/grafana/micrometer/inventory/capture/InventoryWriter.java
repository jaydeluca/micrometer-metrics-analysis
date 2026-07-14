package com.grafana.micrometer.inventory.capture;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.grafana.micrometer.inventory.model.Inventory;
import com.grafana.micrometer.inventory.model.TierCoverage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** Serializes an {@link Inventory} to pretty JSON and prints a coverage summary to stdout. */
public final class InventoryWriter {

    private final ObjectMapper mapper = new ObjectMapper()
            .enable(SerializationFeature.INDENT_OUTPUT)
            // do not collapse null baseUnit/description — an absent unit is a captured fact
            .disable(SerializationFeature.FAIL_ON_EMPTY_BEANS);

    public void write(Inventory inventory, Path out) throws IOException {
        if (out.getParent() != null) {
            Files.createDirectories(out.getParent());
        }
        // trailing newline keeps the committed file POSIX-clean and diff-friendly
        Files.writeString(out, mapper.writeValueAsString(inventory) + "\n");
    }

    public void printSummary(Inventory inventory, Path out) {
        var h = inventory.header();
        System.out.println("──────────────────────────────────────────────");
        System.out.printf("Micrometer %s · JDK %s · %s%n", h.micrometerVersion(), h.jdk(), h.os());
        System.out.printf("Captured %d distinct meters → %s%n", h.totalMeters(), out);
        for (TierCoverage c : h.coverage()) {
            System.out.printf(
                    "  tier %d: %d/%d binders ok, %d meters%s%n",
                    c.tier(),
                    c.bindersSucceeded(),
                    c.bindersAttempted(),
                    c.metersCaptured(),
                    c.bindersFailed() == 0 ? "" : " (" + c.bindersFailed() + " FAILED)");
            for (String f : c.failures()) {
                System.out.println("      ! " + f);
            }
        }
        System.out.println("──────────────────────────────────────────────");
    }
}
