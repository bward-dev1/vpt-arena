"""Write the `vpt_arena` datapack: duel arenas, kits, round start/end, and [ARENA] log lines for rewards.

    python tools/make_datapack.py --out <world>/datapacks/vpt_arena --format 101

Then in game or over RCON: /reload, /function vpt:arena/build (once per world).
A round: tag the two players (vpt_p plus vpt_a / vpt_b), then
/function vpt:duel/start_<kit>. The pack prints `[ARENA] round_start`, and
`<winner> [ARENA] win` when one player dies (or, in sumo, touches the water).
LiveEnv drives all of this from configs/arenas.json.

Written for the 26.x datapack format (singular folders, min/max_format,
snake_case gamerules). Not yet loaded on a real server: check the server log
for function errors after /reload.
"""
import argparse
import json
from pathlib import Path

X, Y, Z = 10000, 100, 10000  # arena centre, far from spawn
KITS = {
    "sword": ["give @s minecraft:iron_sword", "item replace entity @s armor.head with minecraft:iron_helmet",
              "item replace entity @s armor.chest with minecraft:iron_chestplate",
              "item replace entity @s armor.legs with minecraft:iron_leggings",
              "item replace entity @s armor.feet with minecraft:iron_boots"],
    "classic": ["give @s minecraft:iron_sword", "give @s minecraft:fishing_rod", "give @s minecraft:bow",
                "give @s minecraft:arrow 8", "item replace entity @s armor.head with minecraft:iron_helmet",
                "item replace entity @s armor.chest with minecraft:iron_chestplate",
                "item replace entity @s armor.legs with minecraft:iron_leggings",
                "item replace entity @s armor.feet with minecraft:iron_boots"],
    "uhc": ["give @s minecraft:diamond_sword", "give @s minecraft:bow", "give @s minecraft:arrow 16",
            "give @s minecraft:golden_apple 3", "give @s minecraft:lava_bucket", "give @s minecraft:water_bucket",
            "give @s minecraft:cobblestone 64", "give @s minecraft:diamond_axe",
            "item replace entity @s armor.head with minecraft:diamond_helmet",
            "item replace entity @s armor.chest with minecraft:diamond_chestplate",
            "item replace entity @s armor.legs with minecraft:diamond_leggings",
            "item replace entity @s armor.feet with minecraft:diamond_boots"],
    "bow": ["give @s minecraft:bow", "give @s minecraft:arrow 32",
            "item replace entity @s armor.chest with minecraft:leather_chestplate"],
    "sumo": [],
    "boxing": ["effect give @s minecraft:resistance infinite 2 true"],
}


def files():
    f = {}
    f["function/load.mcfunction"] = "\n".join([
        "scoreboard objectives add vpt_deaths deathCount",
        "scoreboard objectives add vpt_state dummy",
        "gamerule immediate_respawn true",
        "say [ARENA] loaded",
    ])
    f["function/arena/build.mcfunction"] = "\n".join([
        f"forceload add {X - 16} {Z - 16} {X + 16} {Z + 16}",
        f"schedule function vpt:arena/build2 60t",
    ])
    f["function/arena/build2.mcfunction"] = "\n".join([
        # open duel floor with a barrier ring
        f"fill {X - 12} {Y - 1} {Z - 12} {X + 12} {Y - 1} {Z + 12} minecraft:smooth_stone",
        f"fill {X - 12} {Y} {Z - 12} {X + 12} {Y + 6} {Z + 12} minecraft:air",
        f"fill {X - 13} {Y - 1} {Z - 13} {X + 13} {Y + 6} {Z + 13} minecraft:barrier hollow",
        f"fill {X - 12} {Y - 1} {Z - 12} {X + 12} {Y - 1} {Z + 12} minecraft:smooth_stone",
        # sumo: small platform over water, 40 blocks east
        f"fill {X + 34} {Y - 4} {Z - 8} {X + 46} {Y - 2} {Z + 8} minecraft:water",
        f"fill {X + 37} {Y - 1} {Z - 3} {X + 43} {Y - 1} {Z + 3} minecraft:white_concrete",
        "say [ARENA] built",
    ])
    for kit, cmds in KITS.items():
        f[f"function/kit/{kit}.mcfunction"] = "\n".join(["clear @s", "effect clear @s"] + cmds + [
            "effect give @s minecraft:instant_health 1 10 true", "effect give @s minecraft:saturation 1 10 true"])
        sumo = kit == "sumo"
        ax, bx = (X + 38, X + 42) if sumo else (X - 6, X + 6)
        f[f"function/duel/start_{kit}.mcfunction"] = "\n".join([
            "scoreboard players reset @a[tag=vpt_p] vpt_deaths",
            "tag @a remove vpt_dead",
            f"execute as @a[tag=vpt_p] run function vpt:kit/{kit}",
            f"tp @a[tag=vpt_a,limit=1] {ax} {Y} {Z} -90 0",
            f"tp @a[tag=vpt_b,limit=1] {bx} {Y} {Z} 90 0",
            "gamemode survival @a[tag=vpt_p]",
            f"scoreboard players set #mode vpt_state {2 if sumo else 1}",
            "scoreboard players set #running vpt_state 1",
            f"say [ARENA] round_start {kit}",
        ])
    f["function/tick.mcfunction"] = "\n".join([
        "execute if score #running vpt_state matches 1 run function vpt:duel/check",
    ])
    f["function/duel/check.mcfunction"] = "\n".join([
        "tag @a[tag=vpt_p,scores={vpt_deaths=1..}] add vpt_dead",
        f"execute if score #mode vpt_state matches 2 as @a[tag=vpt_p] at @s if block ~ ~ ~ minecraft:water "
        "run function vpt:duel/knocked",
        "execute if entity @a[tag=vpt_p,tag=vpt_dead] run function vpt:duel/end",
    ])
    f["function/duel/knocked.mcfunction"] = "\n".join([
        "tag @s add vpt_dead",
        "execute as @a[tag=vpt_p,tag=!vpt_dead] run say [ARENA] knockoff",
    ])
    f["function/duel/end.mcfunction"] = "\n".join([
        "scoreboard players set #running vpt_state 0",
        "execute as @a[tag=vpt_p,tag=!vpt_dead] run say [ARENA] win",
        "execute as @a[tag=vpt_p,tag=vpt_dead] run say [ARENA] loss",
        "execute unless entity @a[tag=vpt_p,tag=!vpt_dead] run say [ARENA] draw",
        "tag @a remove vpt_dead",
    ])
    return f


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--format", type=int, default=101, help="data pack format major version of your server")
    args = ap.parse_args(argv)
    out = Path(args.out)
    (out / "data" / "vpt").mkdir(parents=True, exist_ok=True)
    (out / "pack.mcmeta").write_text(json.dumps({"pack": {"description": "VPT Arena duels",
                                                           "min_format": [args.format, 0],
                                                           "max_format": args.format}}, indent=1))
    for rel, text in files().items():
        p = out / "data" / "vpt" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n")
    tags = out / "data" / "minecraft" / "tags" / "function"
    tags.mkdir(parents=True, exist_ok=True)
    (tags / "load.json").write_text(json.dumps({"values": ["vpt:load"]}))
    (tags / "tick.json").write_text(json.dumps({"values": ["vpt:tick"]}))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
