"""Bounded, normalized service-aware scheduling rewards."""


def minimum_feasible_execution_reward(config):
    """Worst possible accepted-task reward under configured component bounds."""
    return (config["completion_bonus"]
            - config["reward_carbon_weight"] * config["carbon_clip"]
            - config["lambda_latency"])


def rejection_reward(config):
    return -(config["rejection_penalty"] + config["lambda_sla"])


def validate_reward_config(config):
    if config["carbon_scale_g"] <= 0 or config["carbon_clip"] <= 0:
        raise ValueError("carbon normalization scale and clip must be positive")
    if min(config["completion_bonus"], config["reward_carbon_weight"], config["lambda_latency"],
           config["lambda_sla"], config["rejection_penalty"], config["defer_penalty"]) < 0:
        raise ValueError("reward coefficients must be nonnegative")
    if config["defer_penalty"] <= 0:
        raise ValueError("deferral must have a positive per-step cost")
    if config["forced_defer_penalty"] < 0:
        raise ValueError("forced deferral penalty must be nonnegative")
    if -config["forced_defer_penalty"] >= minimum_feasible_execution_reward(config):
        raise ValueError("forced deferral must score below any feasible execution")
    if rejection_reward(config) >= minimum_feasible_execution_reward(config):
        raise ValueError("rejection must score below the worst feasible execution")


def execution_reward(carbon_gco2e, latency_seconds, remaining_deadline_seconds, config):
    carbon_norm = min(max(carbon_gco2e, 0.0) / config["carbon_scale_g"], config["carbon_clip"])
    latency_norm = min(max(latency_seconds, 0.0) / max(remaining_deadline_seconds, 1.0), 1.0)
    components = {
        "completion": config["completion_bonus"],
        "carbon": -config["reward_carbon_weight"] * carbon_norm,
        "latency": -config["lambda_latency"] * latency_norm,
        "sla": 0.0,
        "rejection": 0.0,
        "defer": 0.0,
    }
    return sum(components.values()), components


def deferral_reward(config):
    components = {"completion": 0.0, "carbon": 0.0, "latency": 0.0,
                  "sla": 0.0, "rejection": 0.0, "defer": -config["defer_penalty"]}
    return sum(components.values()), components


def terminal_rejection_reward(config):
    components = {"completion": 0.0, "carbon": 0.0, "latency": 0.0,
                  "sla": -config["lambda_sla"],
                  "rejection": -config["rejection_penalty"], "defer": 0.0}
    return sum(components.values()), components


def forced_defer_reward(config):
    """Penalize an owner action that deferred until the environment had to place it."""
    components = {"completion": 0.0, "carbon": 0.0, "latency": 0.0,
                  "sla": 0.0, "rejection": 0.0,
                  "defer": -config["forced_defer_penalty"]}
    return sum(components.values()), components
