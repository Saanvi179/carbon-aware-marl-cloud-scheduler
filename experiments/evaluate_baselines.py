from environment.cloud_environment import CloudEnvironment, Region
from environment.resource_manager import Resources
from environment.network_model import NetworkModel
from environment.task_generator import synthetic_workload
from environment.carbon_model import CarbonModel, synthetic_carbon_profiles
from schedulers.fcfs import FCFSScheduler
from schedulers.greedy_carbon import GreedyCarbonScheduler


def make_environment():
    regions = [
        Region("north", Resources(8, 64, 256), 420, 300, 100, 1.20, 1.0),
        Region("west", Resources(6, 48, 192), 180, 280, 90, 1.15, 1.15),
        Region("east", Resources(10, 80, 384), 320, 330, 110, 1.25, 0.9),
    ]
    profiles = {"north": [420, 380, 460, 400], "west": [180, 220, 160, 210],
                "east": [320, 300, 360, 310]}
    return CloudEnvironment(regions, NetworkModel(), slot_seconds=60, max_deferrals=2,
                            carbon_model=CarbonModel(profiles, {r.name: r.carbon_intensity for r in regions}))


def make_phase25_environment(dynamic_carbon=True, profile_slots=96):
    """Phase 2.5 environment with a full-horizon synthetic carbon profile."""
    regions = [
        Region("north", Resources(8, 64, 256), 420, 300, 100, 1.20, 1.0),
        Region("west", Resources(6, 48, 192), 180, 280, 90, 1.15, 1.15),
        Region("east", Resources(10, 80, 384), 320, 330, 110, 1.25, 0.9),
    ]
    defaults = {r.name: r.carbon_intensity for r in regions}
    profiles = synthetic_carbon_profiles(profile_slots) if dynamic_carbon else {
        name: [value] * profile_slots for name, value in defaults.items()}
    return CloudEnvironment(regions, NetworkModel(), slot_seconds=60, max_deferrals=2,
                            carbon_model=CarbonModel(profiles, defaults))


def environment_for_config(config):
    mode = config.get("carbon_profile_mode")
    if mode == "dynamic_synthetic":
        return make_phase25_environment(dynamic_carbon=True)
    if mode == "static_control":
        return make_phase25_environment(dynamic_carbon=False)
    return make_environment()


if __name__ == "__main__":
    for name, scheduler in (("FCFS", FCFSScheduler()),
                            ("Greedy carbon", GreedyCarbonScheduler())):
        result = make_environment().run(synthetic_workload(), scheduler)
        print(f"{name}: {result['totals']}")
