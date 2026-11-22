# VPT Arena trailer: design logic

Outputs: `trailer-30.mp4` (1920x1080, 30 fps, 75 s, the main one), `trailer-60.mp4` (the same edit at 60 fps), `trailer-vertical.mp4` (1080x1920, 30 fps, 30 s). All H.264, yuv420p, under 24 MB. Everything is built in the cloud by `.github/workflows/trailer.yml`.

## The idea

The honest story is the strong one: one neural network, 23 PvP modes, and a baseline that has won nothing. So the trailer is a launch-trailer build (quiet, tension, drop, payoff) wrapped around one number: **0 wins**. The viewer is shown what the system is (cold open), how it plays (sees, acts, knows the mode), the scale (23 modes at once), where it learns (cloud), what to watch (dashboard, rounds), and where to go (watch it learn live). Nothing is faked: the zero is real, so the ending says "From 0 wins." and means it.

## Time is the only clock

Music is 128 BPM in 4/4. One beat = 0.46875 s, one bar = 1.875 s. 40 bars = exactly 75 s. The vertical cut is 16 bars = exactly 30 s. Every animation is a function of time in seconds (`useCurrentFrame() / fps`), never of frame numbers, so the 30 fps and 60 fps renders are the same edit and line up with the same audio. Scene boundaries are on bar lines. Hard cuts inside scenes are on beats or on every second beat. 30 fps does not divide a beat evenly (14.06 frames), so cut times are rounded to the nearest frame; the error is under 17 ms, below what is audible.

## Storyboard, main cut (75 s)

| Time | Bars | Section (music) | Scene | Intent |
|---|---|---|---|---|
| 0.0-7.5 | 0-3 | Intro: soft kick, pad, hats in bar 4 | Cold open. "One network." / "plays Minecraft PvP" / "23" / "PvP modes." / "the untouched baseline has won" / "Zero." / `0 / 69`. One idea per bar, text slams in on the beat. | Set the premise and plant the zero. Dark and quiet so the first hit of the groove feels big. |
| 7.5-15.0 | 4-7 | Groove: four-on-floor kick, claps on 2 and 4, off-beat open hat, rolling bass | "It sees. It acts. It knows the mode. It starts from VPT." One full-frame clip per bar, an inset of the agent's 128x128 view, a live-looking key strip at 20 Hz. | How it plays, in four bars, over real gameplay. |
| 15.0-22.5 | 8-11 | Groove (same) | Design diagram: FRAME -> VPT <- MODE embedding, -> ACTIONS. Boxes appear on beats 0, 2, 4, 6; pulses travel the arrows after beat 8. | The design logic: one set of weights, a learned embedding says which of 23 modes it is in. Blurred gameplay behind it keeps it from feeling like a slide. |
| 22.5-30.0 | 12-15 | Groove 2: adds 16th-note arp | Build, part 1. Tiles multiply on every beat (1, 2, 3 ...). Bar texts: "One brain." "23 PvP modes." "Duels. Bed Wars. SkyWars." "The Bridge. UHC. Spleef." | Split-screen of many modes, growing. |
| 30.0-37.5 | 16-19 | Riser: noise sweep, snare roll 8ths then 16ths then 32nds | Build, part 2. Up to all 23 tiles. Last beat (37.03-37.5) is a full blackout with a growing line; the music also drops out for that beat. | Tension, then the gap before the drop. |
| 37.5-45.0 | 20-23 | Drop: kick, clap, 16th hats, 16th bass, offbeat chord stabs, impact | The wall: all 23 clips in a 6x4 grid, one tile lit every half beat, mode name and its real result in the lower bar. | The payoff: scale. A bright frame sweeps the grid with the hats. |
| 45.0-52.5 | 24-27 | Drop (same) | Hero cuts every two beats, alternating one big clip with a three-way split. Eight cuts. | Fast, rhythmic variety; the clips are the actual evaluation clips. |
| 52.5-60.0 | 28-31 | Breakdown: kick at half level, pad, arp, long bass | Cloud. 12 worker cells light one per beat (real job names, modes, step counts), then Federated Averaging, then Evaluate All 23 Modes, with a step counter. | Where the learning happens, at a calmer pace so the numbers can be read. |
| 60.0-67.5 | 32-35 | Breakdown, last bar adds a snare build | Dashboard fly-through: Overview, Dashboard, Simulate, Live screenshots tilt in, one per bar, plus the round timeline (baseline, round 0, "training now", "next"). | Shows the product is real and public; the timeline frames "round by round". |
| 67.5-75.0 | 36-39 | Drop (2 bars), final impact (bar 38), tail | "From 0 wins." The live view appears at bar 37. On the final impact (71.25 s): flash, "Watch it learn live.", `vpt-arena.vercel.app`. Fade to black over the last 1.2 s. | The call to action lands on the biggest hit of the track. |

## Storyboard, vertical cut (30 s, 16 bars)

0-3.75 cold open (compressed to two bars) / 3.75-11.25 how it plays (four clips, one per bar) / 11.25-15 tile build with last-beat blackout / 15-22.5 wall then hero cuts (wall is a 3x8 grid; split screens are stacked rows) / 22.5-26.25 cloud / 26.25-30 finale, impact on 28.1 s. The pipeline diagram and dashboard fly-through are dropped: on a phone, one idea per beat reads better than a diagram.

## Typography

- Headlines: Space Grotesk 700, uppercase, tight tracking (-2.5% of size). Wide and heavy so it survives a phone screen.
- Data and labels: JetBrains Mono 500/700, uppercase for chips. Mono signals "this is a measured number".
- Sizes: 150-230 px for the single idea on screen, 90 px for scene titles, 24-46 px for the mono lines. Never more than three type sizes in a shot.
- Motion: every headline slams in from 170% scale to 100% with a spring (damping 11, stiffness 190) and fades in over about 60 ms. It is on the beat, so the text is the percussion you can see.

## Colour

The site's accent green and blue, on a dark ground for the launch-trailer look (the site itself has moved to a light theme; its screenshots appear in the trailer as bright cards on the dark scene, which makes them pop): background `#080b0f`, panels `#121720`, lines `#232b38`, text `#e8ecf2`, muted `#9aa5b5`, accent green `#7cc4a0`, accent blue `#7ea8f0`. One extra: glow `#b8ffd9` for flashes. Red `#ec7b7b` is used for exactly one thing: zero wins. Green = the agent/system, red = the baseline's zero, so the meaning of colour never changes.

## Voxel / grid motif

A 60 px square-cell grid sits behind every non-footage scene. On each beat, 16 random cells (seeded by beat number, so deterministic) flash green and fade. A perspective floor grid scrolls toward the camera. The same squares appear in the logo mark. The idea is a block world without using any game art: squares, not a logo or texture.

## Treatment of the clips

The source clips are 320x180. Stretching them looks cheap, so they are treated as a look: nearest-neighbour scaling (chunky pixels, on purpose), contrast and saturation up, a green-to-blue duotone wash blended with `screen`, 1 px scanlines every 3 px, a vignette, accent corner brackets with a thin inner frame, and a label chip with mode name and result ("baseline 0/3 wins"). On each beat the picture punches in by 3.5 percent. The 23-clip wall is composited once with ffmpeg (`xstack`) in the workflow, so the render decodes one video instead of 23 at 60 fps.

## Motion rules

1. Cuts on beats only (one per beat in builds, one per two beats in hero cuts, one per bar in the story scenes).
2. Every new scene or hit gets a flash (screen-blended glow, 0.2-0.5 s decay), strongest on the drop and the final hit.
3. Things build, then hold: diagrams add one element per beat and then pulse; they never move while being read.
4. Hits are paired with silence. The last beat of the riser has no sound and no picture; the drop comes back with both.
5. No emoji, no Minecraft logo or art. "Minecraft" is used only as a fact ("plays Minecraft PvP", "Minecraft 1.16.5").

## Music

Original, synthesised in `trailer/audio/make_music.py` with numpy only (no samples, no copyrighted material). A minor, loop Am - F - C - G, one chord per bar.

- Kick: sine with a pitch sweep from 176 to 46 Hz plus a click. Clap: noise with three short bursts. Hats: high-passed noise, closed on the beat, open on the off-beat.
- Bass: sine plus two harmonics, soft-clipped; 8th notes in the groove, 16ths in the drop.
- Stabs: three detuned saws per chord note, short and bright, on 16ths 0, 3, 6, 10, 12 of the bar in the drop. Arp: plucked sines on 8ths or 16ths.
- Sidechain: pads, bass, stabs and arp duck 70 percent on every kick and recover over 0.28 s, which is what makes the groove pump.
- Riser: a rising saw sweep plus noise, with a snare roll that doubles in density twice.
- Master: tanh soft clip, peak at about -1.5 dBFS, 10 ms fade-in, 1.4 s fade-out.

Sections (bars): intro 0-3, groove 4-11, groove 2 12-15, riser 16-19 (last beat silent), drop 20-27, breakdown 28-35, drop 36-37, final impact 38, tail 39. The vertical edit uses the same parts at half length (intro 2 bars, groove 4, riser 2, drop 4, breakdown 2, drop 1, impact 1).

## How real data drives the numbers

`trailer/tools/prep.py` runs in the cloud right before the render and reads the live site and the GitHub releases. Nothing on screen is typed in by hand:

- `0 / 69` and the "From 0 wins." line come from `data.json` (`rounds`): the sum of `wins` and `episodes` across all modes of the baseline evaluation.
- Per-mode chips ("baseline 0/3 wins", "return -5.2") come from the same file, for the release each clip came from. If round 0 has clips, those are used for that mode and the chip says round 0 instead.
- Worker cells (job names, modes, steps) and the "game steps trained so far" counter are the `summary.json` files on the `round-N` releases.
- The round timeline is `data.rounds.rounds` (tag, wins, games, Elo); the next slots are labelled "training now" and "next", not guessed.
- Screens are real headless-Chrome captures of `#/overview`, `#/dashboard`, `#/simulate`, `#/live`; the live card uses `/live/frame.jpg` when the stream is on, else the Live tab capture.

Re-running the workflow later gives the same edit with updated numbers and newer clips.

## Why these choices

- 128 BPM: fast enough to feel like a trailer, and 40 bars land on exactly 75 s with no stretching.
- 75 s: long enough to explain the system, short enough to hold a viewer. The vertical cut is 30 s because social players cut earlier.
- Quiet start: the zero needs space. A loud first bar would bury it.
- Diagram early, wall later: explaining after a hook loses people; explaining before the payoff gives the payoff meaning.
- The ending is the zero again, in red, followed by the call to action in green: the story is "start here, watch it change".
- Honest framing over hype: the agent mostly loses today. The trailer never shows a win it did not get; the clips are labelled with their results.
- 30 fps main with a 60 fps twin: the edit is time-based, so the player can toggle with no re-timing.

---

# Cinematic cut (`trailer-cinematic-30.mp4`, `trailer-cinematic-60.mp4`)

A second, separate cut for people who want the story rather than the hype. Same project, different grammar: slow, letterboxed, scored by an orchestra, cut on phrases. 96 s, 1920x1080 with a 2.39:1 picture (1920x802) between 139 px black bars, 30 fps and a 60 fps twin of the same edit. Workflow: `.github/workflows/trailer-cinematic.yml` (one machine, one run). Source: `src/cine/`, score: `audio/cinematic_score.py`, prep: `tools/prep_cine.py`.

## Intent

Hype says "look how big". Cinematic says "look how honest". The agent has never won a game, and every cut keeps saying so, while showing the one thing that is real and moving: mean return rising from -3.58 to -1.57 over rounds 0 to 4. The viewer should leave thinking "that is early, and it is going somewhere", not "that is a product ad".

## Music is the clock

75 BPM, 4/4, bar = 3.2 s, 30 bars = 96.0 s exactly. Cuts land on bar lines (phrases) and a scene is 2 to 9 bars; shots inside a scene are 3 to 6 s (one or two bars). No beat cutting. Instruments are real samples (MuseScore_General SoundFont through FluidSynth, produced with the music-lab toolkit: piano, strings, cellos and basses, horns, tuba, choir pad, timpani, orchestra kit), then a mix and master (-16 LUFS, true peak -3.9 dB, orchestral tonal profile checked). The hype track is a different thing and is synthesised; this one is not.

| Bars | Time | Music | Picture |
|---|---|---|---|
| 1-4 | 0-12.8 | Low drone, then sparse piano, then a quiet arpeggio | Black. "It has never won a game." Then the baseline's first fight: duels (sword), slow push-in, ramp to 30 percent speed and back |
| 5-10 | 12.8-32 | Strings enter and swell, cellos at bar 6, light ostinato from bar 8 | "One network." over a soft-focus clip; a parallax pair with "Built on OpenAI's VPT."; "It sees 128 x 128 pixels. It presses keys twenty times a second." |
| 11-19 | 32-60.8 | Ostinato and piano, timpani single hits from bar 13, horn theme from bar 15, timpani roll in bars 18-19 | "Round by round." Round 0 vs the latest round side by side in the two modes that improved most, with the mean-return line drawing slowly; then the line full-screen with "-3.58 -> -1.57" |
| 20-24 | 60.8-76.8 | Full orchestra: horn theme, tuba, choir, timpani, orchestra drums | OpenAI's final released model vs the latest round in duels (sword); the scratch-trained model vs the latest round (classic duels); the ladder of mean returns. All stop on the last beat of bar 24 |
| 25 | 76.8-80 | The hush: one low piano note | Cut to black. "0 wins." |
| 26-27 | 80-86.4 | Quiet piano, strings begin to rise | "Yet." in amber. Hard cut to black at 83.2, on the bar |
| 28-30 | 83.2-96 | Resolution in C major, horns carry the theme, final chord rings out | "Watch it learn live.", the URL, then the live card; fade to black 94.4-96 |

## Picture

- **Letterbox:** 2.39:1 inside the 1080p frame. Wide, calm, unmistakably "film" without needing any other trick.
- **Pace:** shots of 3 to 6 s. Slow push-ins (about 4 to 16 percent over the shot) with a few tens of pixels of drift. Parallax in the premise: a blurred, darkened copy of one clip moving one way behind a sharp, smaller one moving the other.
- **Speed ramps:** footage is cut into 0.5 s slices, each played at a rate taken from a smoothstep ramp, with the source position carried across so there is no jump. Typical ramp: 1.0 -> 0.3 over 1.3 s, hold 2 s, back to 1.0 over 1.4 s, placed mid-fight. The 60 fps render uses the interpolated `clip60-*` files where the release has them, so slow-motion stays smooth.
- **Grade:** teal wash in the shadows and amber in the highlights (soft-light layers plus a teal multiply at the bottom), contrast up slightly, saturation down. The footage is 480x270, so it is left soft rather than sharpened or pixelated: soft plus grain reads as film.
- **Grain and vignette:** 8 frames of temporal noise generated by ffmpeg, cycled at 12 Hz at 15 percent overlay; a soft radial vignette.
- **Depth of field:** title cards sit over the same footage blurred 16-20 px that racks to 6-7 px as the title arrives. Text stays sharp.
- **Cuts to black:** four, all on bar lines: after the cold open line, at 12.8 (before the strings), at 76.8 (the hush) and at 83.2 (after "Yet.").

## Type and colour

Cormorant Garamond (serif, 500) at large sizes with lining numerals, light tracking, mixed case; JetBrains Mono at 16-26 px, upper case, 0.12-0.2 em tracking for data. Warm off-white `#e9e4d8` on near-black; one accent, amber `#e3a64f`, used for the "later" side of every comparison, the chart line, "Yet." and the URL. Teal is only in the grade. No bold, no kinetic text: titles fade up 14 px and defocus in over 1.4 s.

## Real numbers, read at render time

`tools/prep_cine.py` downloads `eval.json` for `baseline`, every `round-N`, `openai-rl-2x` and the latest `scratch-N`, and computes the mean of per-mode returns, total wins and games. Nothing is typed in:

- the chart and the title numbers (-3.58, -1.57) come from those means (round 0 to the latest round);
- the ladder bars (baseline -3.49, scratch -4.27, OpenAI -3.37, latest round -1.57) are the same means;
- "scores higher in N of 8 duels" counts duel modes where the latest round's return beats `openai-rl-2x`;
- "It has never won a game" is only shown if every evaluated release has 0 wins (otherwise the text switches to the real count), and "0 wins." / "Yet." follow the latest round's total;
- the two comparison modes are the two with the largest return gain from the first round to the latest;
- every label shows the per-mode return for that policy.

Return is the evaluation's shaped return, not a win count; the cut says "return", never "better player", and the closing beat is the honest one: 0 wins, yet.

## Why these choices

- Phrase cuts and long shots give the numbers time to be read and the music time to breathe.
- Side-by-side in the same mode is the only fair way to show improvement with 3-game evaluations: the viewer compares two policies on identical ground instead of trusting a line.
- The rivals come after the learning, not before: first show it moves, then show where it stands.
- The hush before "Yet." is a missing sound, not a loud one. After a full-orchestra bar, one low piano note is the loudest thing the film can do.
- Letterbox, grain, teal/amber and serif type are cinema's own shorthand; used sparingly they signal "this is a story" without any cinematic-looking claims.
