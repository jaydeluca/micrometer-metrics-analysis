package com.grafana.micrometer.inventory.model;

import java.util.List;

/**
 * Per-tier attempted-vs-captured accounting so silent coverage gaps are visible: a binder that
 * fails to construct or bind shows up here as a failure rather than vanishing from the inventory.
 */
public record TierCoverage(
        int tier,
        int bindersAttempted,
        int bindersSucceeded,
        int bindersFailed,
        int metersCaptured,
        List<String> failures) {
}
