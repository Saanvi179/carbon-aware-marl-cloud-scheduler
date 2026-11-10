"""Fixed illustrative inter-region network characteristics."""
class NetworkModel:
    def __init__(self, links=None):
        self.links = links or {}

    def migration_latency(self, source: str, destination: str, dataset_gb: float) -> float:
        if source == destination:
            return 0.0
        bandwidth_gbps, rtt_seconds = self.links.get((source, destination), (2.0, 0.08))
        return dataset_gb * 8.0 / bandwidth_gbps + rtt_seconds
