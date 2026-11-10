from environment.agent_api import ActionType, RegionAction


class GreedyCarbonScheduler:
    """Choose the feasible region with the least emissions and small latency penalties."""
    def __init__(self, latency_weight=0.01):
        self.latency_weight = latency_weight

    def _rank(self, task, candidate, region_names):
        return (candidate["carbon"] + self.latency_weight *
                (candidate["migration"] + candidate["execution"]),
                region_names.index(candidate["region"]))

    def propose(self, observation, candidates, region_names):
        own = next((c for c in candidates if c["region"] == observation.region), None)
        if own is not None:
            return RegionAction(observation.region, ActionType.EXECUTE_LOCAL)
        if observation.region == observation.task.source_region and candidates:
            target = min(candidates, key=lambda c: self._rank(observation.task, c, region_names))["region"]
            return RegionAction(observation.region, ActionType.MIGRATE, target)
        return RegionAction(observation.region, ActionType.DEFER)

    def resolve(self, task, proposals, candidates, region_names, force=False):
        if not candidates:
            return None
        proposed_targets = set()
        by_region = {c["region"]: c for c in candidates}
        for action in proposals:
            if action.action == ActionType.EXECUTE_LOCAL:
                proposed_targets.add(action.agent_region)
            elif action.action == ActionType.MIGRATE:
                proposed_targets.add(action.target_region)
        selected = [by_region[name] for name in proposed_targets if name in by_region]
        pool = selected or candidates
        return min(pool, key=lambda c: self._rank(task, c, region_names))

    def choose(self, task, candidates, region_names, force=False):
        return self.resolve(task, [], candidates, region_names, force)
