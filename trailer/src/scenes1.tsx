import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile, useVideoConfig, random} from 'remotion';
import {BAR, BEAT, C, F} from './theme';
import {At, Brand, Chip, Clip, Flash, Mode, Slam, VoxelBG, clamp01, clipStart, easeOut, fmtInt, pulse, useT, useTall} from './components';

export const byId = (P: any, id: string): Mode => P.modes.find((m: Mode) => m.id === id) || P.modes[0];
const upper = (s: string) => s.toUpperCase();

// ---------- 1. Cold open: ONE NETWORK / 23 MODES / ZERO WINS ----------
export const Intro: React.FC<{P: any}> = ({P}) => {
  const t = useT();
  const tall = useTall();
  const k = tall ? 0.5 : 1;
  const S = (b: number) => b * k * BEAT;
  const bt = t / (BEAT * k);
  const sz = tall ? 150 : 230;
  const {wins, games} = P.stats;
  return (
    <AbsoluteFill>
      <VoxelBG />
      <div style={{position: 'absolute', left: tall ? 60 : 80, top: tall ? 70 : 60}}>
        <Brand size={tall ? 34 : 30} />
      </div>
      <AbsoluteFill style={{padding: tall ? 70 : 140, justifyContent: 'center', gap: 10}}>
        {bt < 4 && (
          <>
            <Slam at={0} size={sz * 0.85}>One network.</Slam>
            <Slam at={S(2)} size={sz * 0.4} mono color={C.accent}>plays Minecraft PvP</Slam>
          </>
        )}
        {bt >= 4 && bt < 8 && (
          <>
            <Slam at={S(4)} size={sz * 2} glow color={C.accent}>23</Slam>
            <Slam at={S(5)} size={sz * 0.8}>PvP modes.</Slam>
          </>
        )}
        {bt >= 8 && bt < 12 && (
          <>
            <Slam at={S(8)} size={sz * 0.3} mono color={C.muted}>the untouched baseline has won</Slam>
            <Slam at={S(9)} size={sz * 1.6} color={C.bad}>{wins === 0 ? 'Zero.' : fmtInt(wins)}</Slam>
          </>
        )}
        {bt >= 12 && (
          <>
            <Slam at={S(12)} size={sz * 1.25} mono>
              <span style={{color: wins === 0 ? C.bad : C.accent}}>{fmtInt(wins)}</span> / {fmtInt(games)}
            </Slam>
            <Slam at={S(13)} size={sz * 0.26} mono color={C.muted}>evaluation games won by the unmodified VPT model</Slam>
            <Slam at={S(14.5)} size={sz * 0.3} color={C.accent}>An AI learning PvP from scratch.</Slam>
          </>
        )}
      </AbsoluteFill>
      {[4, 8, 12].map((b) => (
        <Flash key={b} at={S(b)} strength={0.28} />
      ))}
    </AbsoluteFill>
  );
};

const KEYS = ['W', 'A', 'S', 'D', 'SPACE', 'CLICK'];
const Keys: React.FC<{size: number}> = ({size}) => {
  const t = useT();
  const step = Math.floor(t * 20);
  return (
    <div style={{display: 'flex', gap: size * 0.3, alignItems: 'center'}}>
      {KEYS.map((key, i) => {
        const on = random(`${key}-${step}`) > (key === 'W' ? 0.35 : 0.7);
        return (
          <div
            key={key}
            style={{
              fontFamily: F.mono, fontWeight: 700, fontSize: size * 0.55, color: on ? C.bg : C.muted,
              background: on ? C.accent : 'rgba(8,11,15,0.8)', border: `2px solid ${on ? C.glow : C.line}`,
              minWidth: size * (key.length > 1 ? 2.2 : 1.1), height: size * 1.1, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            {key}
          </div>
        );
      })}
      <Chip size={size * 0.5} color={C.blue}>20 Hz</Chip>
    </div>
  );
};

// ---------- 2. How it plays: sees / acts / knows the mode / starts from VPT ----------
const SEES = [
  {id: 'duels_sword', h: 'It sees.', c: '128 x 128 pixel frames'},
  {id: 'bedwars_solo', h: 'It acts.', c: 'keys + mouse, 20 times a second'},
  {id: 'skywars_solo', h: 'It knows the mode.', c: 'a learned game-mode embedding'},
  {id: 'the_bridge', h: 'It starts from VPT.', c: "OpenAI's Video PreTraining model"},
];
export const Sees: React.FC<{P: any}> = ({P}) => {
  const t = useT();
  const tall = useTall();
  const {width, height} = useVideoConfig();
  const bi = Math.min(3, Math.floor(t / BAR));
  const pad = tall ? 50 : 90;
  return (
    <AbsoluteFill style={{background: C.bg}}>
      {SEES.map((s, i) => {
        const m = byId(P, s.id);
        return (
          <At key={s.id} from={i * BAR} dur={BAR}>
            <Clip m={m} start={clipStart(m, i + 3)} big style={{left: 0, top: 0, width, height}} />
            <Clip m={m} start={clipStart(m, i + 3)} label={false} punch={false} style={{right: pad, top: pad, width: tall ? 250 : 270, height: tall ? 250 : 270}} />
          </At>
        );
      })}
      <AbsoluteFill style={{background: 'linear-gradient(90deg, rgba(8,11,15,0.82), rgba(8,11,15,0.25) 60%, transparent)'}} />
      <div style={{position: 'absolute', right: pad, top: pad + (tall ? 262 : 282)}}>
        <Chip size={tall ? 17 : 18}>agent view / 128 x 128 input</Chip>
      </div>
      <div style={{position: 'absolute', left: pad, top: tall ? 560 : 330, display: 'flex', flexDirection: 'column', gap: 18}}>
        {SEES.map((s, i) =>
          i === bi ? (
            <React.Fragment key={s.id}>
              <Slam at={i * BAR} size={tall ? 120 : 170} glow>{s.h}</Slam>
              <Slam at={i * BAR + BEAT} size={tall ? 36 : 44} mono color={C.accent}>{s.c}</Slam>
            </React.Fragment>
          ) : null
        )}
      </div>
      <div style={{position: 'absolute', left: pad, bottom: tall ? 120 : 70}}>
        <Keys size={tall ? 46 : 54} />
      </div>
      {[0, 1, 2, 3].map((i) => (
        <Flash key={i} at={i * BAR} strength={0.35} />
      ))}
    </AbsoluteFill>
  );
};

// ---------- 3. Design logic: frame -> VPT (+ mode embedding) -> actions (wide only) ----------
const Box: React.FC<{x: number; y: number; w: number; h: number; at: number; title: string; sub: string; accent?: boolean; color?: string}> = ({x, y, w, h, at, title, sub, accent, color = C.accent}) => {
  const t = useT();
  if (t < at) return null;
  const p = easeOut((t - at) / 0.25);
  return (
    <div
      style={{
        position: 'absolute', left: x, top: y + (1 - p) * 30, width: w, height: h, opacity: p,
        background: 'rgba(18,23,32,0.92)', border: `${accent ? 4 : 2}px solid ${color}`,
        boxShadow: accent ? `0 0 60px rgba(124,196,160,${0.25 + 0.2 * pulse(t, 4)})` : 'none',
        padding: 24, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 10,
      }}
    >
      <div style={{fontFamily: F.head, fontWeight: 700, fontSize: accent ? 76 : 52, color: C.text, letterSpacing: -2}}>{title}</div>
      <div style={{fontFamily: F.mono, fontWeight: 500, fontSize: 24, color: C.muted, lineHeight: 1.25}}>{sub}</div>
    </div>
  );
};
const Arrow: React.FC<{x1: number; y1: number; x2: number; y2: number; at: number; packets?: boolean}> = ({x1, y1, x2, y2, at, packets}) => {
  const t = useT();
  if (t < at) return null;
  const p = easeOut((t - at) / 0.3);
  const ex = x1 + (x2 - x1) * p;
  const ey = y1 + (y2 - y1) * p;
  const ph = (t / BEAT) % 1;
  return (
    <>
      <svg style={{position: 'absolute', inset: 0}} width="100%" height="100%">
        <line x1={x1} y1={y1} x2={ex} y2={ey} stroke={C.accent} strokeWidth={5} />
        {p > 0.95 && <circle cx={x2} cy={y2} r={9} fill={C.accent} />}
        {packets && p > 0.95 && <rect x={x1 + (x2 - x1) * ph - 9} y={y1 + (y2 - y1) * ph - 9} width={18} height={18} fill={C.glow} />}
      </svg>
    </>
  );
};
export const Pipeline: React.FC<{P: any}> = ({P}) => {
  const t = useT();
  const m = byId(P, 'bedwars_squads');
  const {width, height} = useVideoConfig();
  const B = (n: number) => n * BEAT;
  const live = t > B(8);
  const cap = t < BAR * 2 ? 'Frames in, actions out.' : t < BAR * 3 ? 'A learned embedding tells it which of the 23 modes it is in.' : 'One network. One set of weights. No per-mode agents.';
  return (
    <AbsoluteFill>
      <VoxelBG dim={0.7} floor={false} />
      <Clip m={m} start={clipStart(m, 5)} label={false} punch={false} style={{left: 0, top: 0, width, height, opacity: 0.16}} />
      <div style={{position: 'absolute', left: 140, top: 90}}>
        <Slam at={0} size={92}>One brain. One embedding per mode.</Slam>
      </div>
      <Box x={140} y={380} w={440} h={250} at={0} title="FRAME" sub="128 x 128 pixels from the game screen" />
      <Arrow x1={580} y1={505} x2={760} y2={505} at={B(1)} packets={live} />
      <Box x={760} y={350} w={440} h={310} at={B(2)} accent title="VPT" sub="OpenAI's Video PreTraining foundation model" />
      <Arrow x1={1200} y1={505} x2={1380} y2={505} at={B(7)} packets={live} />
      <Box x={1380} y={380} w={400} h={250} at={B(6)} title="ACTIONS" sub="keys + mouse, 20 times a second" />
      <Box x={760} y={760} w={440} h={190} at={B(4)} color={C.blue} title="MODE" sub="learned embedding: 1 of 23 game modes" />
      <Arrow x1={980} y1={760} x2={980} y2={662} at={B(5)} packets={live} />
      <div style={{position: 'absolute', left: 140, bottom: 80}}>
        <Slam key={cap} at={t < BAR * 2 ? 0 : t < BAR * 3 ? BAR * 2 : BAR * 3} size={46} mono color={C.accent}>{cap}</Slam>
      </div>
      <Flash at={0} strength={0.3} />
      <Flash at={BAR * 2} strength={0.3} />
    </AbsoluteFill>
  );
};
