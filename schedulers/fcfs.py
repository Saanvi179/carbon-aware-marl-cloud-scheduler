from environment.agent_api import ActionType, RegionAction


class FCFSScheduler:
    """FCFS task ordering, with deterministic local-first proposal resolution."""
    def propose(self, observation, candidates, region_names):
        if observation.local_feasible:
            return RegionAction(observation.region, ActionType.EXECUTE_LOCAL)
        if observation.region == observation.task.source_region:
            destinations = [c["region"] for c in candidates if c["region"] != observation.region]
            if destinations:
                target = min(destinations, key=region_names.index)
                return RegionAction(observation.region, ActionType.MIGRATE, target)
        return RegionAction(observation.region, ActionType.DEFER)

    def resolve(self, task, proposals, candidates, region_names, force=False):
        if not candidates:
            return None
        by_region = {c["region"]: c for c in candidates}
        claimed = set()
        for action in proposals:
            target = (action.agent_region if action.action == ActionType.EXECUTE_LOCAL else
                      action.target_region if action.action == ActionType.MIGRATE else None)
            if target in by_region and target not in claimed:
                claimed.add(target)
        if not claimed:
            claimed.update(by_region)
        return min((by_region[name] for name in claimed),
                   key=lambda c: (c["region"] != task.source_region, region_names.index(c["region"])))

    # Backward-compatible convenience for direct baseline callers.
    def choose(self, task, candidates, region_names, force=False):
        return self.resolve(task, [], candidates, region_names, force)
