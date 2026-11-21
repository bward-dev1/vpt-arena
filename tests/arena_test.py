"""Arena tasks + sim_env reward logic against a fake MineStudio sim (no Minecraft needed).

    python3 -m tests.arena_test
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vpt_arena.rl import arena_tasks  # noqa: E402
from vpt_arena.rl.sim_env import ArenaSimEnv  # noqa: E402


class FakeInner:
    def __init__(self, outer):
        self.outer = outer
        self.cmds = []

        class AS:
            @staticmethod
            def no_op():
                d = {k: 0 for k in ("attack", "back", "forward", "jump", "left", "right", "sneak", "sprint", "use",
                                    "inventory", *[f"hotbar.{i}" for i in range(1, 10)])}
                d["camera"] = np.zeros(2)
                return d
        self.action_space = AS()

    def execute_cmd(self, c):
        self.cmds.append(c)
        if c.startswith("/tp @p"):
            x, y, z = (float(v) for v in c.split()[2:5])
            self.outer.info["player_pos"] = {"x": x + 0.5, "y": y, "z": z + 0.5, "pitch": 0, "yaw": -90}  # MC centres integer x/z
        return {}, 0, False, dict(self.outer.info)


class FakeSim:
    def __init__(self):
        self.info = {"health": 20.0, "damage_dealt": 0.0, "kill_entity": {}, "mine_block": {}, "pickup": {},
                     "craft_item": {}, "player_pos": {"x": 0, "y": 64, "z": 0}}
        self.env = FakeInner(self)
        self.script = []

    def reset(self):
        return {"image": np.zeros((128, 128, 3), np.uint8)}, dict(self.info)

    def step(self, a):
        if self.script:
            self.script.pop(0)(self.info)
        return {"image": np.zeros((128, 128, 3), np.uint8)}, 0.0, False, False, {**self.info}


def main():
    from vpt_arena.rl.sim_env import absolutize
    assert absolutize("/fill ~-10 ~-1 ~-10 ~10 ~-1 ~10 minecraft:stone", 3000, 200, 4000) == \
        "/fill 2990 199 3990 3010 199 4010 minecraft:stone"
    assert absolutize("/setblock ~18 ~ ~0 minecraft:red_bed[facing=east,part=foot]", 3000, 200, 4000).startswith(
        "/setblock 3018 200 4000 ")
    assert "3007 201 4000 {PersistenceRequired" in absolutize(arena_tasks.mob("zombie", 7, 0, "iron_sword")[0], 3000, 200, 4000)
    n = arena_tasks.check()
    print(f"{n} tasks, one per mode")
    # every task builds without errors
    for mode in arena_tasks.TASKS:
        env = ArenaSimEnv(mode, sim=FakeSim())
        f = env.reset()
        assert f.shape == (128, 128, 3)
        _, r, d, info = env.step({"forward": 1})
        assert np.isfinite(r)

    # sword duel: damage, kill -> win
    sim = FakeSim()
    env = ArenaSimEnv("duels_sword", sim=sim)
    env.reset()
    assert any(c.startswith("/summon zombie") for c in sim.env.cmds)
    sim.script = [lambda i: i.update(damage_dealt=40.0), lambda i: i.update(kill_entity={"minecraft:zombie": 1})]
    _, r1, d1, _ = env.step({"attack": 1})
    _, r2, d2, inf = env.step({"attack": 1})
    w = arena_tasks.TASKS["duels_sword"].w
    assert abs(r1 - (40 * w["damage_dealt"])) < 1e-6 and not d1
    assert d2 and inf["won"] and abs(r2 - (w["kill"] + w["win"])) < 1e-6, (r2, inf)

    # fall out of a sky arena = death
    sim = FakeSim()
    env = ArenaSimEnv("bedwars_solo", sim=sim)
    env.reset()
    y0 = env.origin[1]
    for _ in range(11):  # position checks start after a short settling period
        env.step({})
    sim.script = [lambda i: i.update(player_pos={**i["player_pos"], "y": y0 - 20})]
    _, r, d, inf = env.step({})
    assert d and inf["died"] and r < 0

    # bridge progress then goal
    sim = FakeSim()
    env = ArenaSimEnv("the_bridge", sim=sim)
    env.reset()
    ox, oz = env.origin[0], env.origin[2]
    sim.script = [lambda i: i.update(player_pos={"x": ox + 10, "y": i["player_pos"]["y"], "z": oz}),
                  lambda i: i.update(player_pos={"x": ox + 24, "y": i["player_pos"]["y"], "z": oz})]
    _, r1, d1, _ = env.step({"forward": 1})
    _, r2, d2, inf = env.step({"forward": 1})
    tw = arena_tasks.TASKS["the_bridge"].w
    assert abs(r1 - 10 * tw["progress"]) < 1e-6 and not d1
    assert d2 and inf["won"] and r2 > tw["goal"]

    # bed broken
    sim = FakeSim()
    env = ArenaSimEnv("bedwars_solo", sim=sim)
    env.reset()
    sim.script = [lambda i: i.update(mine_block={"minecraft:red_bed": 1})]
    _, r, d, inf = env.step({"attack": 1})
    assert d and inf["won"] and r >= arena_tasks.TASKS["bedwars_solo"].w["target"]

    # survival curriculum
    sim = FakeSim()
    env = ArenaSimEnv("survival", sim=sim)
    env.reset()
    sim.script = [lambda i: i.update(mine_block={"minecraft:oak_log": 3}), lambda i: i.update(craft_item={"crafting_table": 1})]
    _, r1, _, _ = env.step({"attack": 1})
    _, r2, _, _ = env.step({"use": 1})
    assert r1 == 3.0 and r2 == 2.0, (r1, r2)

    # a simulator failure ends the episode and recovers instead of crashing
    sim = FakeSim()
    env = ArenaSimEnv("duels_sword", sim=sim)
    env.reset()
    def boom(i):
        raise TimeoutError("timed out")
    sim.script = [boom]
    _, r, d, inf = env.step({})
    assert d and inf.get("sim_error") and env.recoveries == 1 and not env.started
    env.reset()

    # TNT Run removes the block you stood on a few steps later
    sim = FakeSim()
    env = ArenaSimEnv("tnt_run", sim=sim)
    env.reset()
    n0 = len(sim.env.cmds)
    for _ in range(arena_tasks.TASKS["tnt_run"].decay_floor + 1):
        env.step({})
    assert any(c.startswith("/setblock") and c.endswith("cave_air") for c in sim.env.cmds[n0:]), sim.env.cmds[n0:]

    # timeout
    sim = FakeSim()
    env = ArenaSimEnv("tnt_run", sim=sim)
    env.reset()
    for _ in range(arena_tasks.TASKS["tnt_run"].max_steps - 1):
        _, _, d, _ = env.step({})
        assert not d
    _, r, d, inf = env.step({})
    assert d and inf["won"]
    print("arena checks passed")


if __name__ == "__main__":
    main()
