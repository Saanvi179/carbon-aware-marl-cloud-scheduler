import unittest

from environment.cloud_environment import CloudEnvironment, Region
from environment.network_model import NetworkModel
from environment.resource_manager import Resources
from environment.task_generator import Task
from environment.carbon_model import CarbonModel
from schedulers.forecast_mpc import ForecastAwareMPCScheduler, CarbonForecastProvider
from schedulers.greedy_carbon import GreedyCarbonScheduler


class ForecastAwareMPCTests(unittest.TestCase):
    def setUp(self):
        self.regions = [
            Region("north", Resources(8, 64, 256), 400.0, 300.0, 100.0, 1.2, 1.0),
            Region("west", Resources(6, 48, 192), 200.0, 280.0, 90.0, 1.15, 1.15),
            Region("east", Resources(10, 80, 384), 300.0, 330.0, 110.0, 1.25, 0.9),
        ]
        self.network = NetworkModel({
            ("north", "west"): (2.0, 0.08),
            ("north", "east"): (2.0, 0.08),
            ("west", "east"): (2.0, 0.08),
        })

    def test_forecast_provider_strict_horizon_enforcement(self):
        profiles = {
            "north": [400.0, 350.0, 300.0, 250.0, 200.0, 150.0, 100.0],
            "west": [200.0, 190.0, 180.0, 170.0, 160.0, 150.0, 140.0],
            "east": [300.0, 290.0, 280.0, 270.0, 260.0, 250.0, 240.0],
        }
        provider = CarbonForecastProvider(profiles, {"north": 400.0, "west": 200.0, "east": 300.0}, horizon_slots=3)

        # Within horizon queries succeed
        self.assertEqual(provider.get_forecast("north", current_slot=1, target_slot=1), 350.0)
        self.assertEqual(provider.get_forecast("north", current_slot=1, target_slot=3), 250.0)
        self.assertEqual(provider.get_forecast("north", current_slot=1, target_slot=4), 200.0)

        # Query in the past raises ValueError
        with self.assertRaisesRegex(ValueError, "past"):
            provider.get_forecast("north", current_slot=2, target_slot=1)

        # Query beyond horizon (current_slot 1 + horizon 3 = max slot 4; slot 5 is forbidden) raises ValueError
        with self.assertRaisesRegex(ValueError, "Information leakage"):
            provider.get_forecast("north", current_slot=1, target_slot=5)

    def test_task_slack_and_urgency_evaluation(self):
        scheduler = ForecastAwareMPCScheduler(forecast_horizon_hours=2.0, slot_seconds=900, urgency_slack_threshold_seconds=1800.0)
        
        # Candidate at slot 0: execution=600s, migration=0s. Total=600s.
        candidate = {"region": "north", "migration": 0.0, "execution": 600.0, "start": 0.0, "end": 600.0}

        # Urgent task: deadline is 1200s (slack is 600s < 1800s threshold)
        urgent_task = Task("u1", 0, 1.0, 4.0, 16.0, 0.1, 1200.0, 600.0, "north")
        is_urg, slack = scheduler.is_urgent(urgent_task, [candidate], slot=0, force=False)
        self.assertTrue(is_urg)
        self.assertEqual(slack, 600.0)

        # Delay-tolerant task: deadline is 7200s (slack is 6600s >> 1800s threshold)
        relaxed_task = Task("r1", 0, 1.0, 4.0, 16.0, 0.1, 7200.0, 600.0, "north")
        is_urg_rel, slack_rel = scheduler.is_urgent(relaxed_task, [candidate], slot=0, force=False)
        self.assertFalse(is_urg_rel)
        self.assertEqual(slack_rel, 6600.0)

        # Force flag forces urgency
        is_urg_forced, _ = scheduler.is_urgent(relaxed_task, [candidate], slot=0, force=True)
        self.assertTrue(is_urg_forced)

    def test_deferral_when_forecast_reveals_lower_carbon_valley(self):
        # Current slot 0 carbon is high (500), but slot 1 carbon is much lower (150)
        profiles = {
            "north": [500.0, 150.0, 150.0, 150.0],
            "west": [500.0, 150.0, 150.0, 150.0],
            "east": [500.0, 150.0, 150.0, 150.0],
        }
        scheduler = ForecastAwareMPCScheduler(
            forecast_horizon_hours=2.0,
            slot_seconds=900,
            carbon_forecast=profiles,
            urgency_slack_threshold_seconds=1800.0,
            deferral_saving_threshold=0.10,
        )

        relaxed_task = Task("r1", 0, 1.0, 4.0, 16.0, 0.1, 7200.0, 600.0, "north")
        candidates = [
            {"region": "north", "migration": 0.0, "execution": 600.0, "start": 0.0, "end": 600.0,
             "energy": 0.5, "carbon": 250.0, "available_gpus": 8.0, "queue_length": 0, "queued_work_seconds": 0.0}
        ]

        # Should recommend deferral (return None) to exploit the 150 gCO2e/kWh valley in slot 1
        decision = scheduler.resolve(relaxed_task, [], candidates, ["north", "west", "east"], force=False)
        self.assertIsNone(decision)
        self.assertEqual(scheduler.task_deferrals["r1"], 1)

    def test_urgent_task_does_not_defer_even_if_forecast_is_lower(self):
        profiles = {
            "north": [500.0, 50.0, 50.0, 50.0],
            "west": [500.0, 50.0, 50.0, 50.0],
            "east": [500.0, 50.0, 50.0, 50.0],
        }
        scheduler = ForecastAwareMPCScheduler(
            forecast_horizon_hours=2.0,
            slot_seconds=900,
            carbon_forecast=profiles,
            urgency_slack_threshold_seconds=1800.0,
        )

        # Urgent task with only 600s slack (< 1800s threshold)
        urgent_task = Task("u1", 0, 1.0, 4.0, 16.0, 0.1, 1200.0, 600.0, "north")
        candidates = [
            {"region": "north", "migration": 0.0, "execution": 600.0, "start": 0.0, "end": 600.0,
             "energy": 0.5, "carbon": 250.0, "available_gpus": 8.0, "queue_length": 0, "queued_work_seconds": 0.0}
        ]

        # Must NOT defer! Must place immediately to avoid SLA violation
        decision = scheduler.resolve(urgent_task, [], candidates, ["north", "west", "east"], force=False)
        self.assertIsNotNone(decision)
        self.assertEqual(decision["region"], "north")

    def test_terminal_fallback_after_max_deferrals(self):
        scheduler = ForecastAwareMPCScheduler(max_deferrals=2)
        task = Task("t1", 0, 1.0, 4.0, 16.0, 0.1, 7200.0, 600.0, "north")
        candidates = [
            {"region": "north", "migration": 0.0, "execution": 600.0, "start": 0.0, "end": 600.0,
             "energy": 0.5, "carbon": 250.0, "available_gpus": 8.0, "queue_length": 0, "queued_work_seconds": 0.0}
        ]
        # Force placement (task has reached max_deferrals)
        decision = scheduler.resolve(task, [], candidates, ["north", "west", "east"], force=True)
        self.assertIsNotNone(decision)
        self.assertEqual(decision["region"], "north")

    def test_congestion_aware_candidate_ranking(self):
        scheduler = ForecastAwareMPCScheduler(congestion_weight=0.1)
        # Two regions with identical carbon and latency, but north has heavy queue and 0 available GPUs,
        # while west has 0 queue and 6 available GPUs.
        candidates = [
            {"region": "north", "migration": 0.0, "execution": 600.0, "energy": 0.5, "carbon": 100.0,
             "available_gpus": 0.0, "queue_length": 4, "queued_work_seconds": 1200.0},
            {"region": "west", "migration": 0.0, "execution": 600.0, "energy": 0.5, "carbon": 100.0,
             "available_gpus": 6.0, "queue_length": 0, "queued_work_seconds": 0.0},
        ]
        # West must be ranked higher (lower score) due to lower congestion
        rank_north = scheduler.rank_candidate(candidates[0], ["north", "west", "east"])
        rank_west = scheduler.rank_candidate(candidates[1], ["north", "west", "east"])
        self.assertLess(rank_west[0], rank_north[0])

    def test_simulator_integration_synthetic(self):
        profiles = {
            "north": [400.0, 200.0, 100.0, 100.0],
            "west": [300.0, 180.0, 120.0, 120.0],
            "east": [350.0, 250.0, 150.0, 150.0],
        }
        carbon_model = CarbonModel(profiles, {"north": 400.0, "west": 300.0, "east": 350.0})
        env = CloudEnvironment(self.regions, self.network, slot_seconds=900, carbon_model=carbon_model)

        # Task arrives at slot 0 with ample deadline (slot 3 = 2700s)
        tasks = [
            Task("task-1", 0, 2.0, 8.0, 32.0, 0.1, 3600.0, 600.0, "north"),
            Task("task-2", 0, 2.0, 8.0, 32.0, 0.1, 3600.0, 600.0, "west"),
        ]

        scheduler = ForecastAwareMPCScheduler(
            forecast_horizon_hours=2.0,
            slot_seconds=900,
            carbon_forecast=profiles,
            urgency_slack_threshold_seconds=1200.0,
        )

        result = env.run(tasks, scheduler)
        self.assertEqual(result["totals"]["completed"], 2)
        self.assertEqual(result["totals"]["rejected"], 0)
        self.assertEqual(result["totals"]["sla_violations"], 0)

    def test_multi_horizon_differentiation_and_lookahead_depth(self):
        """Verify that 2h (8 slots) and 4h (16 slots) evaluate genuinely different horizons.

        The profiles are constructed so the carbon valley begins at slot 9 (beyond 2h=8 slots
        but within 4h=16 slots). The 2h scheduler should NOT observe the valley; the 4h
        scheduler SHOULD, and therefore the two schedulers must make different decisions.
        """
        # Valley starts at slot 9 (index 9 in 0-based profile). 2h horizon covers slots 0-8
        # (inclusive), so slot 9 is exactly one step beyond 2h.
        profiles = {
            "north": [500.0] * 9 + [100.0] * 15,  # Valley at slots 9-23 (beyond 2h horizon)
            "west": [500.0] * 24,
            "east": [500.0] * 24,
        }
        # 2h horizon (8 slots)
        scheduler_2h = ForecastAwareMPCScheduler(
            forecast_horizon_hours=2.0,
            slot_seconds=900,
            carbon_forecast=profiles,
            max_deferrals=2,
            enable_reservations=True
        )
        # 4h horizon (16 slots)
        scheduler_4h = ForecastAwareMPCScheduler(
            forecast_horizon_hours=4.0,
            slot_seconds=900,
            carbon_forecast=profiles,
            max_deferrals=2,
            enable_reservations=True
        )

        self.assertEqual(scheduler_2h.horizon_slots, 8)
        self.assertEqual(scheduler_4h.horizon_slots, 16)
        self.assertEqual(scheduler_2h.max_deferrals, scheduler_4h.max_deferrals)
        self.assertEqual(scheduler_2h.max_deferrals, 2)

        # Provider strict horizon checks: 2h cannot query slot 10; 4h can
        with self.assertRaisesRegex(ValueError, "exceeds forecast horizon"):
            scheduler_2h.forecast_provider.get_forecast("north", current_slot=0, target_slot=10)
        # 4h succeeds at slot 10 and sees the valley (100 gCO2e/kWh)
        self.assertEqual(scheduler_4h.forecast_provider.get_forecast("north", current_slot=0, target_slot=10), 100.0)
        # 2h returns 500 at slot 8 (last within horizon) — valley not visible
        self.assertEqual(scheduler_2h.forecast_provider.get_forecast("north", current_slot=0, target_slot=8), 500.0)

        # Task with 4 hours of slack (14400s), uncongested single candidate
        relaxed_task = Task("r_long", 0, 1.0, 4.0, 16.0, 0.1, 14400.0, 600.0, "north")
        candidate = {
            "region": "north", "migration": 0.0, "execution": 600.0, "start": 0.0, "end": 600.0,
            "energy": 0.5, "carbon": 250.0, "available_gpus": 8.0, "queue_length": 0, "queued_work_seconds": 0.0
        }

        # 2h: no valley visible in horizon, no congestion → should NOT defer
        should_defer_2h = scheduler_2h.evaluate_forecast_opportunity(
            relaxed_task, [candidate], slot=0, max_slack=13800.0)
        self.assertFalse(should_defer_2h,
            "2h scheduler must NOT defer when valley is beyond its 8-slot horizon")

        # 4h: valley at slot 9 is visible → should defer
        should_defer_4h = scheduler_4h.evaluate_forecast_opportunity(
            relaxed_task, [candidate], slot=0, max_slack=13800.0)
        self.assertTrue(should_defer_4h,
            "4h scheduler MUST defer to exploit the carbon valley visible within its 16-slot horizon")

    def test_reserved_retry_uses_committed_slot_and_destination_then_releases(self):
        profiles = {"north": [500.0, 500.0, 100.0, 100.0, 100.0],
                    "west": [500.0] * 5, "east": [500.0] * 5}
        env = CloudEnvironment(self.regions, self.network, slot_seconds=900,
            carbon_model=CarbonModel(profiles, {n: p[0] for n, p in profiles.items()}))
        scheduler = ForecastAwareMPCScheduler(forecast_horizon_hours=1.0, slot_seconds=900,
            carbon_forecast=profiles, max_deferrals=4, enable_reservations=True)
        task = Task("reserved", 0, 1, 1, 1, 0.1, 9000, 600, "north")

        result = env.run([task], scheduler)

        defer = next(r for r in result["records"] if r["action"] == "defer")
        placement = next(r for r in result["records"] if r["action"] in ("execute_local", "migrate"))
        self.assertEqual(defer["retry_slot"], 2)
        self.assertEqual(placement["slot"], 2)
        self.assertEqual(placement["region"], "north")
        self.assertEqual(result["totals"]["completed"], 1)
        self.assertFalse(scheduler.task_reserved_slot)
        self.assertEqual(scheduler.future_reservations[("north", 2)]["gpus"], 0.0)

    def test_tentative_reservation_blocks_overlapping_conflicting_candidate(self):
        scheduler = ForecastAwareMPCScheduler(slot_seconds=900, max_deferrals=4)
        reserved_task = Task("reserved", 0, 6, 1, 1, 0.1, 7200, 1200, "north")
        scheduler.tentatively_reserve(reserved_task, "north", 2, execution=1200)
        conflicting = Task("conflict", 0, 3, 1, 1, 0.1, 7200, 1200, "north")
        candidate = {"region": "north", "start": 900, "end": 2100,
                     "region_capacity": {"gpus": 8, "cpu_cores": 64, "memory_gb": 256}}
        self.assertFalse(scheduler.candidate_respects_reservations(conflicting, candidate))
        candidate["start"], candidate["end"] = 0, 600
        self.assertTrue(scheduler.candidate_respects_reservations(conflicting, candidate))

    def test_live_candidate_conflict_redirects_away_from_reserved_capacity(self):
        profiles = {"north": [500.0, 500.0, 100.0, 100.0, 100.0, 100.0],
                    "west": [500.0] * 6, "east": [500.0] * 6}
        env = CloudEnvironment(self.regions, self.network, slot_seconds=900,
            carbon_model=CarbonModel(profiles, {n: p[0] for n, p in profiles.items()}))
        scheduler = ForecastAwareMPCScheduler(forecast_horizon_hours=1.0, slot_seconds=900,
            carbon_forecast=profiles, max_deferrals=4, enable_reservations=True)
        first = Task("holds-six", 0, 6, 4, 16, 0.1, 9000, 1200, "north")
        second = Task("needs-four", 1, 4, 4, 16, 0.1, 9000, 1200, "north")
        result = env.run([first, second], scheduler)
        placements = {r["task_id"]: r for r in result["records"]
                      if r["action"] in ("execute_local", "migrate")}
        self.assertIn("holds-six", placements)
        self.assertIn("needs-four", placements)
        self.assertEqual(placements["holds-six"]["region"], "north")
        self.assertNotEqual(placements["needs-four"]["region"], "north")
        self.assertEqual(result["totals"]["completed"], 2)

    def test_extended_deferral_limit_reaches_later_reserved_slot(self):
        profiles = {"north": [500.0] * 3 + [100.0] * 5,
                    "west": [500.0] * 8, "east": [500.0] * 8}
        env = CloudEnvironment(self.regions, self.network, slot_seconds=900,
            max_deferrals=2, carbon_model=CarbonModel(profiles, {n: p[0] for n, p in profiles.items()}))
        scheduler = ForecastAwareMPCScheduler(forecast_horizon_hours=1.0, slot_seconds=900,
            carbon_forecast=profiles, max_deferrals=4, enable_reservations=True)
        task = Task("later", 0, 1, 1, 1, 0.1, 9000, 600, "north")
        result = env.run([task], scheduler)
        defer = next(r for r in result["records"] if r["action"] == "defer")
        placement = next(r for r in result["records"] if r["action"] in ("execute_local", "migrate"))
        self.assertEqual(defer["retry_slot"], 3)
        self.assertEqual(placement["slot"], 3)
        self.assertEqual(result["totals"]["completed"], 1)

    def test_late_arrival_reserved_horizon_is_processed_to_terminal_state(self):
        profiles = {"north": [500.0] * 12,
                    "west": [500.0] * 10 + [100.0] * 2,
                    "east": [500.0] * 12}
        env = CloudEnvironment(self.regions, self.network, slot_seconds=900,
            max_deferrals=2, carbon_model=CarbonModel(profiles, {n: p[0] for n, p in profiles.items()}))
        scheduler = ForecastAwareMPCScheduler(forecast_horizon_hours=2.0, slot_seconds=900,
            carbon_forecast=profiles, max_deferrals=2, enable_reservations=True)
        task = Task("late", 5, 1, 1, 1, 0.1, 5 * 900 + 10800, 7200, "north")
        result = env.run([task], scheduler)
        self.assertEqual(result["totals"]["completed"] + result["totals"]["rejected"], 1)
        self.assertEqual(result["totals"]["completed"], 1)
        deferred = next(r for r in result["records"] if r["action"] == "defer")
        placed = next(r for r in result["records"] if r["action"] in ("execute_local", "migrate"))
        self.assertEqual(deferred["retry_slot"], 10)
        self.assertEqual(placed["slot"], 10)
        self.assertEqual(placed["region"], "west")
        self.assertEqual(scheduler.deferrals_recommended, 1)

    def test_deadline_urgency_prevents_reservation_past_feasible_slot(self):
        profiles = {name: [500.0, 100.0, 100.0] for name in ("north", "west", "east")}
        env = CloudEnvironment(self.regions, self.network, slot_seconds=900,
            carbon_model=CarbonModel(profiles, {n: p[0] for n, p in profiles.items()}))
        scheduler = ForecastAwareMPCScheduler(forecast_horizon_hours=1.0, slot_seconds=900,
            carbon_forecast=profiles, max_deferrals=4)
        task = Task("urgent", 0, 1, 1, 1, 0.1, 1400, 600, "north")
        result = env.run([task], scheduler)
        self.assertEqual(result["totals"]["completed"], 1)
        self.assertFalse(any(r["action"] == "defer" for r in result["records"]))

    def test_reservation_release_on_rejection_and_rescheduling(self):
        scheduler = ForecastAwareMPCScheduler(slot_seconds=900, max_deferrals=2)
        task = Task("replace", 0, 2, 1, 1, 0.1, 7200, 600, "north")
        scheduler.tentatively_reserve(task, "north", 1, execution=600)
        scheduler.tentatively_reserve(task, "west", 2, execution=600)
        self.assertEqual(scheduler.future_reservations[("north", 1)]["gpus"], 0.0)
        self.assertEqual(scheduler.task_reserved_slot["replace"]["region"], "west")

        impossible = Task("replace", 0, 99, 100, 999, 0.1, 7200, 600, "north")
        env = CloudEnvironment(self.regions, self.network, slot_seconds=900, max_deferrals=0,
            carbon_model=CarbonModel({}, {"north": 400, "west": 200, "east": 300}))
        result = env.run([impossible], scheduler)
        self.assertEqual(result["totals"]["rejected"], 1)
        self.assertNotIn("replace", scheduler.task_reserved_slot)

    def test_tentative_reservation_prevents_capacity_cliff(self):
        """Verify that tentative reservations prevent oversubscribing future slots.

        When a task defers and reserves future capacity, a second task requiring more
        than the remaining capacity in that slot must be redirected to a later slot,
        not placed into the already-committed slot.
        """
        profiles = {
            "north": [500.0, 100.0, 100.0, 100.0],
            "west": [500.0, 500.0, 500.0, 500.0],
            "east": [500.0, 500.0, 500.0, 500.0],
        }
        # Capacity: north has only 8 GPUs
        scheduler = ForecastAwareMPCScheduler(
            forecast_horizon_hours=2.0,
            slot_seconds=900,
            carbon_forecast=profiles,
            max_deferrals=4,
            enable_reservations=True
        )

        candidate = {
            "region": "north", "migration": 0.0, "execution": 600.0, "start": 0.0, "end": 600.0,
            "energy": 0.5, "carbon": 250.0, "available_gpus": 8.0, "queue_length": 0, "queued_work_seconds": 0.0
        }

        # Task 1 needs 6 GPUs — defers to slot 1 and books 6 GPUs.
        task1 = Task("big1", 0, 6.0, 16.0, 64.0, 0.1, 7200.0, 600.0, "north")
        defer1 = scheduler.evaluate_forecast_opportunity(task1, [candidate], slot=0, max_slack=6600.0)
        self.assertTrue(defer1)
        self.assertIn(("north", 1), scheduler.future_reservations)
        self.assertEqual(scheduler.future_reservations[("north", 1)]["gpus"], 6.0)

        # Task 2 needs 4 GPUs (6+4=10 > 8 total north GPUs).
        # Slot 1 in north is full. Scheduler must redirect task2 to a different slot (e.g., slot 2).
        task2 = Task("big2", 0, 4.0, 16.0, 64.0, 0.1, 7200.0, 600.0, "north")
        defer2 = scheduler.evaluate_forecast_opportunity(task2, [candidate], slot=0, max_slack=6600.0)
        # task2 may still defer, but must NOT book into the already-full slot 1 for north
        if defer2:
            north_slot1_gpus = scheduler.future_reservations.get(("north", 1), {}).get("gpus", 0.0)
            self.assertLessEqual(north_slot1_gpus, 8.0,
                "Reservation in north/slot1 must never exceed 8 GPU capacity even after task2 defers")

        # Task 3 needs 2 GPUs (6+2=8 ≤ 8 total) — fits into slot 1.
        task3 = Task("small3", 0, 2.0, 8.0, 32.0, 0.1, 7200.0, 600.0, "north")
        defer3 = scheduler.evaluate_forecast_opportunity(task3, [candidate], slot=0, max_slack=6600.0)
        self.assertTrue(defer3)
        # North/slot1 reservation must now total exactly 8 GPUs (6 + 2)
        self.assertEqual(scheduler.future_reservations[("north", 1)]["gpus"], 8.0)

    def test_reservation_released_on_allocation_and_elapsed_slot(self):
        """Verify that reservations are cleanly released on allocation."""
        profiles = {"north": [500.0, 100.0, 100.0], "west": [500.0, 500.0, 500.0], "east": [500.0, 500.0, 500.0]}
        scheduler = ForecastAwareMPCScheduler(
            forecast_horizon_hours=2.0, slot_seconds=900, carbon_forecast=profiles, enable_reservations=True
        )
        task = Task("t_alloc", 0, 4.0, 16.0, 64.0, 0.1, 7200.0, 600.0, "north")
        candidate = {
            "region": "north", "migration": 0.0, "execution": 600.0, "start": 0.0, "end": 600.0,
            "energy": 0.5, "carbon": 250.0, "available_gpus": 8.0, "queue_length": 0, "queued_work_seconds": 0.0
        }
        # First slot: defer and reserve
        scheduler.resolve(task, [], [candidate], ["north", "west", "east"], force=False)
        self.assertIn("t_alloc", scheduler.task_reserved_slot)
        self.assertEqual(scheduler.future_reservations[("north", 1)]["gpus"], 4.0)

        # Second slot: force allocation now
        candidate_slot1 = {
            "region": "north", "migration": 0.0, "execution": 600.0, "start": 900.0, "end": 1500.0,
            "energy": 0.5, "carbon": 50.0, "available_gpus": 8.0, "queue_length": 0, "queued_work_seconds": 0.0
        }
        res = scheduler.resolve(task, [], [candidate_slot1], ["north", "west", "east"], force=True)
        self.assertIsNotNone(res)
        self.assertNotIn("t_alloc", scheduler.task_reserved_slot)
        self.assertEqual(scheduler.future_reservations[("north", 1)]["gpus"], 0.0)


if __name__ == "__main__":
    unittest.main()
