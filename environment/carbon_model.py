"""Carbon emissions from energy and grid intensity."""
from dataclasses import dataclass
from math import pi, sin


def emissions_gco2e(energy_kwh_value: float, intensity_gco2e_per_kwh: float) -> float:
    return energy_kwh_value * intensity_gco2e_per_kwh


@dataclass
class CarbonModel:
    """Piecewise-constant carbon intensity indexed by simulation slot."""
    profiles: dict[str, list[float]]
    defaults: dict[str, float]
    candidate_forecast_known: bool = True

    def intensity_at(self, region: str, time_seconds: float, slot_seconds: int) -> float:
        profile = self.profiles.get(region, [])
        index = max(0, int(time_seconds // slot_seconds))
        return profile[index] if index < len(profile) else self.defaults[region]


def synthetic_carbon_profiles(slots=96):
    """Deterministic illustrative regional carbon profiles (gCO2e/kWh).

    The smooth daily and shorter-period components are synthetic scenario data,
    not measurements or forecasts. Region-specific phase offsets allow rankings
    to change over time while keeping intensities nonnegative.
    """
    bases = {"north": 420.0, "west": 180.0, "east": 320.0}
    phases = {"north": 0.0, "west": 2.5, "east": 4.3}
    profiles = {}
    for region, base in bases.items():
        phase = phases[region]
        profiles[region] = [
            base * (1.0 + 0.35 * sin(2 * pi * slot / 24.0 + phase)
                    + 0.18 * sin(2 * pi * slot / 8.0 + phase / 2.0))
            for slot in range(slots)
        ]
    return profiles
