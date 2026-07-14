package com.grafana.micrometer.inventory.model;

import java.util.List;

/** The serialized inventory file: a {@link InventoryHeader} followed by the captured meters. */
public record Inventory(InventoryHeader header, List<MeterRecord> meters) {
}
