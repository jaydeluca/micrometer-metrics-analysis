rootProject.name = "micrometer-metrics-inventory"

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

include("capture-core")
include("harness-tier0")
include("harness-tier1")
include("harness-tier2")
include("harness-tier3")
