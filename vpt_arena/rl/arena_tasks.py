"""RL training tasks for every game mode, built inside MineStudio's single-player Minecraft (1.16.5).

Single-player has no second human, so opponents are armed mobs (zombies with
swords and armour, skeletons, vindicators, pillagers). Each task rebuilds the
mode's core skill: melee duels, bow duels, knock-offs, bridging over the void,
breaking a defended bed, grabbing an objective, racing, survival. Arenas are
built in the sky with /fill at a fresh spot each episode, over the void or a
lava pit, so falling off counts.

A task is commands (with {x} {y} {z} = arena origin), opponents, an end rule
and reward weights. sim_env.py turns MineStudio's info stats into rewards.
"""
from dataclasses import dataclass, field

Y = 200  # arena floor height


def armour(tier, slots=("head", "chest", "legs", "feet")):
    names = {"head": "helmet", "chest": "chestplate", "legs": "leggings", "feet": "boots"}
    return [f"/replaceitem entity @p armor.{s} minecraft:{tier}_{names[s]}" for s in slots]


def give(*items):
    out = []
    for it in items:
        name, _, n = it.partition(" ")
        out.append(f"/give @p minecraft:{name} {n or 1}")
    return out


def mob(kind, dx, dz, hand=None, tier=None, extra=""):
    """A persistent armed mob at origin + (dx, 1, dz)."""
    parts = ["PersistenceRequired:1b"]
    if hand:
        parts.append(f'HandItems:[{{id:"minecraft:{hand}",Count:1b}},{{}}]')
    if tier:
        parts.append("ArmorItems:[" + ",".join(f'{{id:"minecraft:{tier}_{p}",Count:1b}}'
                                                for p in ("boots", "leggings", "chestplate", "helmet")) + "]")
    if extra:
        parts.append(extra)
    return f"/summon minecraft:{kind} ~{{dx}} ~1 ~{{dz}} {{{','.join(parts)}}}".replace("{dx}", str(dx)).replace("{dz}", str(dz))


def platform(r, block="smooth_stone", pit=None):
    """Square floor of radius r at the origin; optional lava pit 6 below so falling is fatal and fast."""
    cmds = [f"/fill ~-{r} ~-1 ~-{r} ~{r} ~-1 ~{r} minecraft:{block}", f"/fill ~-{r} ~ ~-{r} ~{r} ~4 ~{r} minecraft:air"]
    if pit:
        cmds.insert(0, f"/fill ~-{r + 6} ~-7 ~-{r + 6} ~{r + 6} ~-7 ~{r + 6} minecraft:lava")
    return cmds


def island(cx, cz, r=3, block="end_stone"):
    return [f"/fill ~{cx - r} ~-1 ~{cz - r} ~{cx + r} ~-1 ~{cz + r} minecraft:{block}"]


@dataclass
class Task:
    mode: str
    setup: list                         # commands run with the player at the arena origin
    opponents: list = field(default_factory=list)
    opponent_types: tuple = ("zombie", "skeleton", "vindicator", "pillager", "husk", "stray", "drowned")
    max_steps: int = 1200               # 60 s at 20 Hz
    sky: bool = True                    # arena in the sky (fall below origin - 8 = out)
    goal: tuple = None                  # (dx, dz) target for races and bridges, reached within 1.5 blocks
    target_blocks: tuple = ()           # mine_block targets (bed, wool, ...)
    w: dict = field(default_factory=dict)  # reward weights (below)


# default weights; tasks override
W = dict(damage_dealt=0.05, damage_taken=-0.05, kill=2.0, death=-5.0, win=10.0, timeout=-2.0,
         progress=0.0, goal=0.0, target=0.0, collect=0.0, alive=0.0)


def T(mode, setup, opponents=(), **kw):
    w = dict(W)
    w.update(kw.pop("w", {}))
    return Task(mode, list(setup), list(opponents), w=w, **kw)


BASE = ["/clear @p", "/effect clear @p", "/effect give @p minecraft:instant_health 1 3 true",
        "/effect give @p minecraft:saturation 1 10 true", "/kill @e[type=!player,distance=..80]"]
SWORD = give("iron_sword") + armour("iron")

TASKS = {t.mode: t for t in [
    T("survival", [], sky=False, max_steps=3000,
      w=dict(collect=1.0, death=-2.0, timeout=0.0, win=0.0)),
    T("duels_sword", BASE + platform(10) + SWORD, [mob("zombie", 7, 0, "iron_sword", "iron")]),
    T("duels_classic", BASE + platform(10) + SWORD + give("fishing_rod", "bow", "arrow 8"),
      [mob("zombie", 8, 0, "iron_sword", "iron"), mob("skeleton", -8, 6, "bow")]),
    T("duels_uhc", BASE + ["/gamerule naturalRegeneration false"] + platform(12) + give(
        "diamond_sword", "bow", "arrow 16", "golden_apple 3", "cobblestone 32", "water_bucket") + armour("diamond"),
      [mob("zombie", 8, 0, "diamond_sword", "diamond"), mob("skeleton", -9, 5, "bow", "iron")], max_steps=2400),
    T("duels_nodebuff", BASE + platform(10) + give("diamond_sword") + armour("diamond") + [
        '/give @p minecraft:splash_potion{Potion:"minecraft:strong_healing"} 8'],
      [mob("vindicator", 7, 0, "iron_axe", "iron")], max_steps=1600),
    T("duels_sumo", BASE + platform(3, "white_concrete", pit=True) + ["/effect give @p minecraft:resistance 60 4 true"],
      [mob("zombie", 2, 0, None, None, "Attributes:[{Name:\"generic.knockback_resistance\",Base:0.0d}]")],
      w=dict(kill=10.0, damage_dealt=0.02, damage_taken=0.0)),
    T("duels_boxing", BASE + platform(8) + ["/effect give @p minecraft:resistance 60 1 true"],
      [mob("zombie", 5, 0)], w=dict(damage_dealt=0.15)),
    T("duels_bow", BASE + platform(14) + give("bow", "arrow 32") + armour("leather", ("chest",)),
      [mob("skeleton", 12, 0, "bow"), mob("stray", -12, 8, "bow")], w=dict(damage_dealt=0.1)),
    T("duels_combo", BASE + platform(10) + give("diamond_sword") + armour("iron") +
      ["/effect give @p minecraft:speed 60 1 true"], [mob("zombie", 7, 0, "iron_sword", "iron"),
                                                       mob("husk", -7, 0, "iron_sword", "iron")]),
    T("build_uhc", BASE + ["/gamerule naturalRegeneration false"] + platform(3) + island(16, 0, 4) + give(
        "diamond_sword", "bow", "arrow 16", "golden_apple 2", "cobblestone 64", "water_bucket") + armour("iron"),
      [mob("skeleton", 16, 0, "bow"), mob("zombie", 17, 2, "iron_sword", "iron")], goal=(16, 0), max_steps=2400,
      w=dict(progress=0.3, goal=3.0)),
    T("bedwars_solo", BASE + platform(3, "white_wool") + island(18, 0, 3, "end_stone") +
      ["/setblock ~18 ~ ~0 minecraft:red_bed[facing=east,part=foot]",
       "/setblock ~19 ~ ~0 minecraft:red_bed[facing=east,part=head]"] + give("stone_sword", "white_wool 64", "shears"),
      [mob("zombie", 17, 2, "stone_sword", "leather")], goal=(18, 0), target_blocks=("red_bed",), max_steps=2400,
      w=dict(progress=0.3, target=15.0, win=5.0)),
    T("bedwars_doubles", BASE + platform(3, "white_wool") + island(18, 0, 3, "end_stone") +
      ["/setblock ~18 ~ ~0 minecraft:blue_bed[facing=east,part=foot]",
       "/setblock ~19 ~ ~0 minecraft:blue_bed[facing=east,part=head]"] + give("iron_sword", "white_wool 64") + armour("chain"),
      [mob("zombie", 17, 2, "iron_sword", "chainmail"), mob("skeleton", 20, -2, "bow")], goal=(18, 0),
      target_blocks=("blue_bed",), max_steps=2400, w=dict(progress=0.3, target=15.0, win=5.0)),
    T("bedwars_squads", BASE + platform(3, "white_wool") + island(18, 0, 4, "end_stone") +
      ["/setblock ~18 ~ ~0 minecraft:green_bed[facing=east,part=foot]",
       "/setblock ~19 ~ ~0 minecraft:green_bed[facing=east,part=head]"] + give("iron_sword", "white_wool 64", "bow",
                                                                             "arrow 8") + armour("iron"),
      [mob("zombie", 17, 2, "iron_sword", "iron"), mob("zombie", 17, -2, "iron_sword", "iron"),
       mob("skeleton", 21, 0, "bow")], goal=(18, 0), target_blocks=("green_bed",), max_steps=3000,
      w=dict(progress=0.3, target=15.0, win=5.0)),
    T("skywars_solo", BASE + platform(2, "grass_block") + island(14, 6, 3, "stone") + give("stone_sword", "cobblestone 48"),
      [mob("zombie", 14, 6, "stone_sword", "chainmail")], goal=(14, 6), max_steps=2400, w=dict(progress=0.3, goal=3.0)),
    T("skywars_doubles", BASE + platform(2, "grass_block") + island(14, 6, 3, "stone") + island(14, -10, 3, "stone") +
      give("iron_sword", "cobblestone 64", "bow", "arrow 8"),
      [mob("zombie", 14, 6, "iron_sword", "iron"), mob("skeleton", 14, -10, "bow")], goal=(14, 6), max_steps=3000,
      w=dict(progress=0.3, goal=3.0)),
    T("the_bridge", BASE + platform(3, "blue_terracotta") + island(24, 0, 3, "red_terracotta") +
      ["/setblock ~24 ~-1 ~0 minecraft:end_portal_frame"] + give("iron_sword", "blue_terracotta 64", "bow", "arrow 4"),
      [mob("zombie", 22, 0, "iron_sword", "leather")], goal=(24, 0), max_steps=2400,
      w=dict(progress=0.4, goal=10.0, win=0.0, kill=1.0)),
    T("uhc", ["/gamerule naturalRegeneration false", "/time set 13000"] + BASE[:-1] + give("stone_sword", "bread 8"),
      [mob("zombie", 6, 6, "stone_sword"), mob("skeleton", -8, 4, "bow")], sky=False, max_steps=3000,
      w=dict(collect=0.5, alive=0.002)),
    T("survival_games", BASE + give("stone_sword", "bow", "arrow 8") + armour("leather"),
      [mob("zombie", 8, 0, "stone_sword", "leather"), mob("zombie", -8, 3, "wooden_sword", "leather"),
       mob("skeleton", 0, 10, "bow")], sky=False, max_steps=3000),
    T("kitpvp", BASE + platform(12) + SWORD + give("bow", "arrow 16", "golden_apple 1"),
      [mob("zombie", 8, 0, "iron_sword", "iron"), mob("zombie", -8, 0, "iron_sword", "iron"),
       mob("vindicator", 0, 9, "iron_axe"), mob("skeleton", 0, -10, "bow")], max_steps=2400, w=dict(win=8.0)),
    T("capture_the_wool", BASE + platform(3) + island(16, 0, 3, "white_concrete") +
      ["/setblock ~16 ~ ~0 minecraft:lime_wool"] + give("iron_sword", "cobblestone 48") + armour("iron"),
      [mob("zombie", 15, 2, "iron_sword", "iron")], goal=(16, 0), target_blocks=("lime_wool",), max_steps=2400,
      w=dict(progress=0.3, target=10.0, win=5.0)),
    T("spleef", BASE + platform(8, "snow_block", pit=True) + give("diamond_shovel"),
      [mob("zombie", 5, 0)], max_steps=1600, w=dict(collect=0.05, kill=10.0, damage_dealt=0.0, alive=0.002)),
    T("tnt_run", BASE + platform(7, "sand", pit=True) + ["/effect give @p minecraft:speed 60 0 true"], [],
      max_steps=1200, w=dict(alive=0.01, win=0.0, timeout=5.0)),
    T("parkour_duel", BASE + platform(1, "quartz_block") + [
        f"/setblock ~{2 + 2 * i} ~-1 ~{(i % 3) - 1} minecraft:quartz_block" for i in range(10)] +
      ["/setblock ~22 ~-1 ~0 minecraft:gold_block"], [], goal=(22, 0), max_steps=1200,
      w=dict(progress=0.5, goal=10.0, win=0.0)),
]}


def check():
    from .. import games
    missing = [m.key for m in games.MODES if m.key not in TASKS]
    assert not missing, f"no RL task for {missing}"
    return len(TASKS)
