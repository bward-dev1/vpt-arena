"""The game modes the agent is trained to play.

Each mode is a conditioning input: the same network plays all of them, and a
learned embedding for (mode, combat ruleset, team size) tells it which one it
is in. Mode 0 is plain survival Minecraft, which is what the VPT foundation
model already does; the conditioning layer starts at zero so an untrained
conditioner leaves VPT's behaviour unchanged.

`events` are the server-side signals the RL phase turns into reward. The
recorder and the arena server plugin emit them with these exact names.
"""
from dataclasses import dataclass, field

RULESETS = ("modern", "legacy")      # 1.9+ attack cooldown vs 1.8 spam-click combat
TEAM_SIZES = (1, 2, 3, 4)            # players per team; 1 = solo / free-for-all


@dataclass(frozen=True)
class GameMode:
    id: int
    key: str
    name: str
    ruleset: str = "modern"
    team_size: int = 1
    summary: str = ""
    events: dict = field(default_factory=dict)   # event name -> reward weight


_W = dict(win=10.0, loss=-10.0, kill=2.0, death=-2.0, damage_dealt=0.05, damage_taken=-0.05)


def _ev(**extra):
    d = dict(_W)
    d.update(extra)
    return d


MODES = [
    GameMode(0, "survival", "Survival (free play)", summary="Plain Minecraft. No arena rules; this is VPT's own task.",
             events=dict(advancement=1.0, death=-2.0)),
    # Duels: 1v1, fixed kit, first to die loses.
    GameMode(1, "duels_sword", "Sword duel", summary="1v1, iron/diamond sword and armour, no rods or bows.", events=_ev()),
    GameMode(2, "duels_classic", "Classic duel", ruleset="legacy",
             summary="1v1, sword + rod + bow, 1.8 combat.", events=_ev()),
    GameMode(3, "duels_uhc", "UHC duel", summary="1v1, no natural regen, golden apples, lava/water buckets, blocks.",
             events=_ev(heal_gapple=0.2)),
    GameMode(4, "duels_nodebuff", "NoDebuff", ruleset="legacy",
             summary="1v1, instant-health splash pots, ender pearls, speed.", events=_ev(pot_hit=0.1)),
    GameMode(5, "duels_sumo", "Sumo", ruleset="legacy",
             summary="1v1 on a small platform, no weapons, knock the other player off.", events=_ev(knockoff=10.0)),
    GameMode(6, "duels_boxing", "Boxing", ruleset="legacy",
             summary="1v1, first to 100 hits wins.", events=_ev(hit=0.1)),
    GameMode(7, "duels_bow", "Bow duel", summary="1v1, bows only.", events=_ev(arrow_hit=0.3)),
    GameMode(8, "duels_combo", "Combo duel", ruleset="legacy",
             summary="1v1, low hit delay, combos.", events=_ev(hit=0.05)),
    GameMode(9, "build_uhc", "Build UHC", summary="1v1 or FFA, blocks, buckets, gapples, bows; bridge and build to fight.",
             events=_ev(heal_gapple=0.2)),
    # Team / objective games.
    GameMode(10, "bedwars_solo", "Bed Wars (solo)", team_size=1,
             summary="Protect your bed, break theirs, buy gear with resources from your generator.",
             events=_ev(bed_broken=6.0, bed_lost=-6.0, final_kill=3.0, resource=0.02, purchase=0.1)),
    GameMode(11, "bedwars_doubles", "Bed Wars (doubles)", team_size=2,
             summary="Bed Wars with a teammate.",
             events=_ev(bed_broken=6.0, bed_lost=-6.0, final_kill=3.0, resource=0.02, purchase=0.1)),
    GameMode(12, "bedwars_squads", "Bed Wars (4v4v4v4)", team_size=4,
             summary="Bed Wars in teams of four.",
             events=_ev(bed_broken=6.0, bed_lost=-6.0, final_kill=3.0, resource=0.02, purchase=0.1)),
    GameMode(13, "skywars_solo", "SkyWars (solo)",
             summary="Islands in the void; loot chests, bridge, fight, last one standing.",
             events=_ev(chest_loot=0.2, void_kill=2.0)),
    GameMode(14, "skywars_doubles", "SkyWars (doubles)", team_size=2,
             summary="SkyWars with a teammate.", events=_ev(chest_loot=0.2, void_kill=2.0)),
    GameMode(15, "the_bridge", "The Bridge",
             summary="Bridge across to the other side and jump in their goal; 5 goals wins.",
             events=_ev(goal=5.0, goal_conceded=-5.0)),
    GameMode(16, "uhc", "UHC (survival games)", team_size=1,
             summary="Natural world, no natural regen; gather, craft, then fight to be last alive.",
             events=_ev(heal_gapple=0.2, advancement=0.3)),
    GameMode(17, "survival_games", "Survival Games",
             summary="Loot chests around a map, fight to be last alive; deathmatch at the end.",
             events=_ev(chest_loot=0.2)),
    GameMode(18, "kitpvp", "KitPvP / FFA", summary="Respawning free-for-all with kits; kills and kill streaks.",
             events=_ev(win=0.0, loss=0.0, streak=0.5)),
    GameMode(19, "capture_the_wool", "Capture the Wool", team_size=4,
             summary="Steal the other team's wool and bring it back to your monument.",
             events=_ev(wool_pickup=2.0, wool_placed=8.0)),
    GameMode(20, "spleef", "Spleef", summary="Break the floor under others; last one up wins.",
             events=dict(win=10.0, loss=-10.0, block_broken=0.02)),
    GameMode(21, "tnt_run", "TNT Run", summary="The floor falls away under you; keep moving, last one up wins.",
             events=dict(win=10.0, loss=-10.0, survive_second=0.05)),
    GameMode(22, "parkour_duel", "Parkour race", summary="Race to the end of a parkour course.",
             events=dict(win=10.0, loss=-10.0, checkpoint=1.0)),
]

BY_KEY = {m.key: m for m in MODES}
BY_ID = {m.id: m for m in MODES}
assert len(BY_KEY) == len(MODES) and len(BY_ID) == len(MODES)


def get(mode):
    if isinstance(mode, GameMode):
        return mode
    if isinstance(mode, int):
        return BY_ID[mode]
    try:
        return BY_KEY[mode]
    except KeyError:
        raise KeyError(f"unknown game mode {mode!r}; known: {', '.join(BY_KEY)}") from None


def cond_ids(mode, ruleset=None, team_size=None):
    """The three integers fed to the conditioner: (mode id, ruleset id, team-size index).

    A recording can override the mode's default ruleset or team size, e.g. a
    sword duel played on a 1.8-combat server.
    """
    m = get(mode)
    r = RULESETS.index(ruleset or m.ruleset)
    t = TEAM_SIZES.index(team_size or m.team_size)
    return (m.id, r, t)
