import React from 'react';
import {AbsoluteFill, Img, random, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont as loadAnton} from '@remotion/google-fonts/Anton';
import {At, ClipRef, Furniture, H, K, Shot, W, clamp, ease, lerp, minus, useT} from './base';
import {clipFor, endWindow, hasShot, shotName, shotRef, startFor} from './footage';

const anton = loadAnton('normal', {weights: ['400'], subsets: ['latin']});
type P = any;
const HEAVY = 'contrast(1.38) saturate(1.12) brightness(0.88)';
const fmtM = (n: number) => (n / 1e6).toFixed(2);

// 80 BPM: hits (seconds) and how hard the camera shakes on them (px in 1920 space)
const SHAKES = [{t: 3.0, a: 10}, {t: 12.0, a: 16}, {t: 15.0, a: 18}, {t: 18.0, a: 22}, {t: 24.0, a: 40}, {t: 33.0, a: 20}, {t: 57.0, a: 18}, {t: 60.0, a: 22}, {t: 75.0, a: 56}, {t: 76.5, a: 64}];

// ---- chunky chrome / steel title type ----
const chrome = (size: number, tint: 'steel' | 'red' | 'gold' = 'steel'): React.CSSProperties => ({
  fontFamily: anton.fontFamily, fontSize: size, lineHeight: 0.96, letterSpacing: '0.015em', textTransform: 'uppercase', textAlign: 'center',
  background: tint === 'red'
    ? 'linear-gradient(180deg,#fff 0%,#ffd8d0 28%,#d4483a 47%,#3d0b07 51%,#ff8e7c 74%,#ffd9d2 100%)'
    : tint === 'gold'
      ? 'linear-gradient(180deg,#fffdf0 0%,#f6dd9a 30%,#c28a22 47%,#3a2406 51%,#f0bd5a 74%,#fff0c8 100%)'
      : 'linear-gradient(180deg,#ffffff 0%,#dfe7ee 28%,#8996a4 46%,#232a32 51%,#9db0c2 70%,#eef5fb 100%)',
  WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', WebkitTextFillColor: 'transparent',
  filter: `drop-shadow(0 ${Math.max(2, size * 0.025)}px 0 rgba(0,0,0,0.85)) drop-shadow(0 0 ${size * 0.14}px ${tint === 'red' ? 'rgba(255,90,70,0.45)' : 'rgba(150,210,255,0.4)'})`,
});

// Anamorphic flare: a long horizontal blue streak, a bright core, a soft bloom and one light streak sweeping across.
const Flare: React.FC<{at: number; strength?: number; y?: number | string}> = ({at, strength = 1, y = '50%'}) => {
  const t = useT();
  if (t < at) return null;
  const k = Math.exp(-(t - at) * 3.0) * strength;
  const g = ease((t - at) / 0.12);
  return (
    <AbsoluteFill style={{pointerEvents: 'none', mixBlendMode: 'screen'}}>
      <div style={{position: 'absolute', left: 0, right: 0, top: y, height: 16, transform: `translateY(-50%) scaleX(${0.15 + 0.85 * g})`, opacity: k,
        background: 'linear-gradient(90deg, rgba(40,120,255,0) 0%, rgba(80,160,255,0.7) 28%, rgba(235,248,255,1) 50%, rgba(80,160,255,0.7) 72%, rgba(40,120,255,0) 100%)', filter: 'blur(6px)'}} />
      <div style={{position: 'absolute', left: 0, right: 0, top: y, height: 3, transform: `translateY(-50%) scaleX(${0.1 + 0.9 * g})`, opacity: k, background: 'linear-gradient(90deg, transparent, #fff 50%, transparent)'}} />
      <div style={{position: 'absolute', left: '50%', top: y, width: 760, height: 760, transform: 'translate(-50%,-50%)', opacity: k * 0.85,
        background: 'radial-gradient(circle, rgba(255,255,255,0.8) 0%, rgba(150,205,255,0.32) 24%, rgba(0,0,0,0) 60%)'}} />
      <div style={{position: 'absolute', top: -120, bottom: -120, width: 240, left: lerp(-400, W + 300, ease((t - at) / 0.8)), transform: 'skewX(-20deg)', opacity: k,
        background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.28), transparent)'}} />
    </AbsoluteFill>
  );
};

const Flash: React.FC<{at: number; strength?: number; dur?: number}> = ({at, strength = 0.8, dur = 0.35}) => {
  const t = useT();
  const k = 1 - clamp((t - at) / dur);
  if (t < at || k <= 0) return null;
  return <AbsoluteFill style={{background: '#fff', opacity: strength * k * k, mixBlendMode: 'screen'}} />;
};

// A title slammed in on a hit: starts large and wide-spaced, snaps down, flares.
const Hit: React.FC<{at: number; children: React.ReactNode; size: number; tint?: 'steel' | 'red' | 'gold'; flare?: number; y?: number | string; style?: React.CSSProperties}> = ({at, children, size, tint = 'steel', flare = 1, y = '50%', style}) => {
  const t = useT();
  if (t < at) return null;
  const p = ease((t - at) / 0.16);
  return (
    <>
      <div style={{...chrome(size, tint), transform: `scale(${lerp(1.45, 1, p)})`, opacity: clamp((t - at) * 30), letterSpacing: `${lerp(0.14, 0.015, p)}em`, ...style}}>{children}</div>
      {flare > 0 && <Flare at={at} strength={flare} y={y} />}
    </>
  );
};

const Small: React.FC<{at: number; until?: number; children: React.ReactNode; size?: number; color?: string; serif?: boolean; italic?: boolean; track?: number; style?: React.CSSProperties}> = ({at, until, children, size = 40, color = K.text, serif = true, italic = false, track = 0.3, style}) => {
  const t = useT();
  const k = ease((t - at) / 0.9) * (until != null ? 1 - ease((t - until) / 0.7) : 1);
  if (t < at || k <= 0) return null;
  return <div style={{fontFamily: serif ? K.serif : K.mono, fontStyle: italic ? 'italic' : 'normal', fontWeight: 500, fontSize: size, letterSpacing: `${track}em`, textTransform: 'uppercase', color, opacity: k, textAlign: 'center', textShadow: '0 2px 24px #000', ...style}}>{children}</div>;
};

const Center: React.FC<{children: React.ReactNode; gap?: number; top?: number}> = ({children, gap = 10, top}) => (
  <AbsoluteFill style={{alignItems: 'center', justifyContent: top != null ? 'flex-start' : 'center', paddingTop: top, gap}}>{children}</AbsoluteFill>
);

const Dark: React.FC<{c: ClipRef; start: number; dur: number; blur?: number; dim?: number; ramp?: any; push?: [number, number]; drift?: [number, number]; grade?: number}> = ({c, start, dur, blur = 0, dim = 0.5, ramp, push = [1.05, 1.16], drift = [0, -30], grade = 1.3}) => (
  <Shot c={c} start={start} dur={dur} blur={blur} dim={dim} ramp={ramp} push={push} drift={drift} filter={HEAVY} grade={grade} />
);

const ref = (P: P, name: string, tag: string, mode: string): ClipRef => shotRef(P, name) || clipFor(P, tag, mode);
const st = (P: P, name: string, len: number, fb = 10) => startFor(P, name, len, fb);

// ---------------- 0 - 12 s: cold open ----------------
const Open: React.FC<{P: P}> = ({P}) => {
  const t = useT();
  const n = Object.keys(P.tags[P.last].per).length;
  const beat = (x: number) => Math.exp(-Math.max(0, ((x % 0.75) + 0.75) % 0.75) * 7);
  const hb = t >= 9 ? Math.max(beat(t - 9), beat(t - 9.35) * 0.7) : 0;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <Flash at={3.0} strength={0.35} dur={0.5} />
      <Center gap={22}>
        <Small at={3.5} until={6.4} size={34} track={0.5}>In a world where</Small>
        <Small at={5.0} until={8.6} size={52} track={0.2}>{`one network plays ${n} game modes...`}</Small>
      </Center>
      {t >= 9 && (
        <At from={9} dur={3}>
          <Dark c={ref(P, 'r4-duels_sword', P.last, 'duels_sword')} start={hasShot(P, 'r4-duels_sword') ? 1.0 : 12} dur={3} dim={1} ramp={[{at: 0, rate: 0.25}, {at: 3, rate: 0.25}]} push={[1.02, 1.2]} drift={[0, -20]} grade={1.3} />
          <div style={{position: 'absolute', left: 70, bottom: 56}}><Small at={0.6} size={20} serif={false} track={0.22} style={{textAlign: 'left'}}>round 4 / duels (sword)</Small></div>
        </At>
      )}
      {t >= 9 && <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 35%, rgba(0,0,0,0.9) 100%)', opacity: 0.35 + 0.55 * hb}} />}
    </AbsoluteFill>
  );
};

// ---------------- 12 - 24 s: three hits, then silence ----------------
const Cards: React.FC<{P: P}> = ({P}) => {
  const rounds = P.rounds.length;
  const n = Object.keys(P.tags[P.last].per).length;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <At from={0} dur={3}>
        <Dark c={ref(P, 'dolly-duels_sword', 'baseline', 'duels_sword')} start={hasShot(P, 'dolly-duels_sword') ? 0.5 : 12} dur={3} blur={6} dim={0.4} />
        <Center><Hit at={0} size={178}>{`${fmtM(P.steps)} million steps.`}</Hit></Center>
      </At>
      <At from={3} dur={3}>
        <Dark c={ref(P, 'r4-spleef', P.last, 'spleef')} start={st(P, 'r4-spleef', 3, 12)} dur={3} blur={6} dim={0.4} />
        <Center><Hit at={0} size={158}>{`${rounds} rounds of training.`}</Hit></Center>
      </At>
      <At from={6} dur={2.25}>
        <Dark c={ref(P, 'dolly-skywars_solo', 'baseline', 'skywars_solo')} start={hasShot(P, 'dolly-skywars_solo') ? 1 : 12} dur={2.25} blur={6} dim={0.4} />
        <Center><Hit at={0} size={196}>{`${n} game modes.`}</Hit></Center>
      </At>
    </AbsoluteFill>
  );
};

// ---------------- 24 - 27 s: 0 WINS ----------------
const Zero: React.FC<{P: P}> = ({P}) => {
  const t = useT();
  const w = P.tags[P.last].wins;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 55%, rgba(120,30,20,0.55), rgba(0,0,0,0) 60%)', opacity: ease((t - 0.1) / 0.8)}} />
      <Flash at={0} strength={1} dur={0.6} />
      <Center><Hit at={0} size={400} tint="red" flare={1.4}>{`${w} wins.`}</Hit></Center>
    </AbsoluteFill>
  );
};

// ---------------- 27 - 36 s: zombies, skeletons, vindicators, none defeated ----------------
const Fought: React.FC<{P: P}> = ({P}) => {
  const parts = [
    {from: 0, dur: 2.25, name: 'r4-duels_sword', mode: 'duels_sword', word: 'zombies.'},
    {from: 2.25, dur: 2.25, name: 'r4-duels_classic', mode: 'duels_classic', word: 'skeletons.'},
    {from: 4.5, dur: 1.5, name: 'r4-duels_sumo', mode: 'duels_sumo', word: 'vindicators.'},
  ];
  return (
    <AbsoluteFill style={{background: '#000'}}>
      {parts.map((q, i) => (
        <At key={q.name} from={q.from} dur={q.dur}>
          <Dark c={ref(P, q.name, P.last, q.mode)} start={st(P, q.name, q.dur, 14)} dur={q.dur} dim={0.55} blur={2} />
          <div style={{position: 'absolute', left: 0, right: 0, top: 70, display: 'flex', justifyContent: 'center'}}>
            <Small at={0.05} size={34} track={0.45}>It has fought</Small>
          </div>
          <Center><Hit at={0.05} size={230} y="52%">{q.word}</Hit></Center>
        </At>
      ))}
      <At from={6} dur={3}>
        <Dark c={ref(P, 'r4-duels_sword', P.last, 'duels_sword')} start={hasShot(P, 'r4-duels_sword') && P.shots['r4-duels_sword'].hurt.length ? Math.max(0, P.shots['r4-duels_sword'].hurt[0] - 1.5) : st(P, 'r4-duels_sword', 3, 20)} dur={3} dim={0.45} ramp={[{at: 0, rate: 0.35}, {at: 3, rate: 0.35}]} blur={3} />
        <Center gap={0}>
          <Small at={0} size={36} track={0.45}>It has defeated</Small>
          <Hit at={0} size={240} tint="red" y="55%">none of them.</Hit>
        </Center>
      </At>
    </AbsoluteFill>
  );
};

// ---------------- 36 - 54 s: three hero shots in slow motion ----------------
const findFall = (P: P): string | undefined => {
  const s = P.shots || {};
  const cand = Object.keys(s).filter((k) => k.startsWith('r4-') && s[k].kind === 'play' && s[k].endT && (s[k].endHp ?? 0) > 1);
  return cand[0] || (hasShot(P, 'r4-duels_sumo') ? 'r4-duels_sumo' : undefined);
};
const Hero: React.FC<{P: P}> = ({P}) => {
  const fall = findFall(P);
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <At from={0} dur={6}>
        <Dark c={fall ? (shotRef(P, fall) as ClipRef) : clipFor(P, P.last, 'duels_sumo')} start={fall ? endWindow(P, fall, 6) : 10} dur={6} dim={1} grade={1.4}
          ramp={[{at: 0, rate: 0.7}, {at: 2.6, rate: 0.7}, {at: 3.4, rate: 0.2}, {at: 6, rate: 0.2}]} push={[1.02, 1.22]} drift={[0, -40]} />
        <Flare at={2.9} strength={0.8} />
      </At>
      <At from={6} dur={6}>
        <Dark c={ref(P, 'r4-bedwars_solo', P.last, 'bedwars_solo')} start={st(P, 'r4-bedwars_solo', 6, 8)} dur={6} dim={1} grade={1.4}
          ramp={[{at: 0, rate: 0.55}, {at: 6, rate: 0.55}]} push={[1.0, 1.26]} drift={[30, -30]} />
        <Flare at={0.1} strength={0.6} />
      </At>
      <At from={12} dur={6}>
        <Dark c={ref(P, 'r4-duels_classic', P.last, 'duels_classic')} start={st(P, 'r4-duels_classic', 6, 14)} dur={6} dim={1} grade={1.4}
          ramp={[{at: 0, rate: 0.8}, {at: 2.2, rate: 0.8}, {at: 3.0, rate: 0.22}, {at: 5.2, rate: 0.22}, {at: 6, rate: 0.6}]} push={[1.04, 1.2]} drift={[-30, 20]} />
        <Flare at={2.4} strength={0.7} />
      </At>
    </AbsoluteFill>
  );
};

// ---------------- 54 - 57 s: pull quotes (in-universe) ----------------
const Stars: React.FC = () => (
  <svg width={360} height={64} viewBox="0 0 360 64">
    {[0, 1, 2, 3, 4].map((i) => (
      <polygon key={i} transform={`translate(${i * 72},0)`} points="32,4 40,24 62,25 45,39 51,60 32,48 13,60 19,39 2,25 24,24" fill="#e8c36a" stroke="#6a4b0c" strokeWidth={2} />
    ))}
  </svg>
);
const Quote: React.FC<{text: string; who: string}> = ({text, who}) => {
  const t = useT();
  const k = ease(t / 0.35);
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', gap: 26, opacity: k, transform: `scale(${lerp(1.06, 1, k)})`}}>
      <Stars />
      <div style={{width: 900, height: 2, background: 'rgba(233,228,216,0.6)'}} />
      <div style={{fontFamily: K.serif, fontStyle: 'italic', fontWeight: 500, fontSize: 96, color: K.text, textAlign: 'center', maxWidth: 1500, lineHeight: 1.05, textShadow: '0 3px 30px #000'}}>{`“${text}”`}</div>
      <div style={{width: 900, height: 2, background: 'rgba(233,228,216,0.6)'}} />
      <div style={{fontFamily: K.mono, fontSize: 28, letterSpacing: '0.35em', color: '#e8c36a', textTransform: 'uppercase'}}>{`— ${who}`}</div>
    </AbsoluteFill>
  );
};
const Quotes: React.FC<{P: P}> = ({P}) => {
  const games = P.tags[P.last].games;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <Dark c={ref(P, 'r4-duels_sword', P.last, 'duels_sword')} start={st(P, 'r4-duels_sword', 3, 20)} dur={3} blur={14} dim={0.3} />
      <At from={0} dur={1.5}><Quote text="It was right behind me." who="The zombie" /></At>
      <At from={1.5} dur={1.5}><Quote text={`Hasn't touched me in ${games} games.`} who="A skeleton" /></At>
    </AbsoluteFill>
  );
};

// ---------------- 57 - 66 s: the boast, then the beat ----------------
const Confetti: React.FC<{at: number}> = ({at}) => {
  const t = useT();
  if (t < at) return null;
  const u = t - at;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {Array.from({length: 70}, (_, i) => {
        const x = random(`cx${i}`) * W;
        const sp = 260 + random(`cs${i}`) * 420;
        const y = -40 + u * sp - random(`cy${i}`) * 200;
        return <div key={i} style={{position: 'absolute', left: x + Math.sin(u * 3 + i) * 30, top: y, width: 10, height: 18, background: ['#e8c36a', '#f5f1e6', '#8fc5ff'][i % 3], transform: `rotate(${u * 300 + i * 40}deg)`, opacity: 0.9}} />;
      })}
    </AbsoluteFill>
  );
};
const Boast: React.FC<{P: P}> = ({P}) => {
  const t = useT();
  const a = P.tags[P.last].mean;
  const b = P.rival ? P.tags[P.rival].mean : 0;
  const sw = Math.sin(t * 0.9) * 22;
  return (
    <AbsoluteFill style={{background: '#04060a'}}>
      <AbsoluteFill style={{background: `conic-gradient(from ${200 + sw}deg at 30% -10%, rgba(0,0,0,0) 0deg, rgba(160,200,255,0.30) 8deg, rgba(0,0,0,0) 18deg), conic-gradient(from ${160 - sw}deg at 70% -10%, rgba(0,0,0,0) 0deg, rgba(255,230,170,0.26) 8deg, rgba(0,0,0,0) 18deg)`}} />
      <At from={0} dur={3}>
        <Flash at={0} strength={0.5} />
        <Center gap={2} top={110}>
          <Small at={0.05} size={50} track={0.3}>It loses less badly than</Small>
          <Hit at={0.05} size={190} y="38%">{"OpenAI's best model."}</Hit>
        </Center>
        {t > 1.4 && (
          <div style={{position: 'absolute', left: 0, right: 0, bottom: 70, display: 'flex', justifyContent: 'center', gap: 160, alignItems: 'flex-end'}}>
            {[{v: a, l: 'Round 4', tint: 'gold' as const}, {v: b, l: 'OpenAI RL 2x', tint: 'steel' as const}].map((x, i) => (
              <div key={x.l} style={{opacity: ease((t - 1.4 - i * 0.25) / 0.4), textAlign: 'center'}}>
                <div style={chrome(170, x.tint)}>{minus(x.v)}</div>
                <div style={{fontFamily: K.mono, fontSize: 24, letterSpacing: '0.3em', color: K.muted, textTransform: 'uppercase'}}>{`${x.l} / mean return`}</div>
              </div>
            ))}
          </div>
        )}
      </At>
      <At from={3} dur={2.25}>
        <Confetti at={0} />
        <Flash at={0} strength={0.6} />
        <Center gap={2}>
          <Small at={0.05} size={54} track={0.3}>It scores higher in</Small>
          <Hit at={0.05} size={290} tint="gold" y="55%">{`${P.duelsBeaten} of ${P.duelsTotal} duels.`}</Hit>
        </Center>
      </At>
    </AbsoluteFill>
  );
};

// ---------------- 66 - 75 s: rising rhythm and a ticking clock ----------------
const Clock: React.FC<{ticks: number}> = ({ticks}) => (
  <svg width={190} height={190} viewBox="-100 -100 200 200">
    <circle r={90} fill="rgba(0,0,0,0.6)" stroke="#e9e4d8" strokeWidth={4} />
    {Array.from({length: 12}, (_, i) => <line key={i} x1={0} y1={-84} x2={0} y2={-72} stroke="#e9e4d8" strokeWidth={3} transform={`rotate(${i * 30})`} />)}
    <line x1={0} y1={8} x2={0} y2={-70} stroke="#ff6a55" strokeWidth={5} strokeLinecap="round" transform={`rotate(${(ticks * 30) % 360})`} />
    <circle r={6} fill="#e9e4d8" />
  </svg>
);
const Montage: React.FC<{P: P}> = ({P}) => {
  const t = useT();
  const s = P.shots || {};
  const play = Object.keys(s).filter((k) => s[k].kind === 'play' && !k.startsWith('hero4k'));
  const doll = Object.keys(s).filter((k) => s[k].kind === 'dolly' && s[k].w === 1920);
  const pool: string[] = [];
  for (let i = 0; i < Math.max(play.length, doll.length); i++) { if (play[i]) pool.push(play[i]); if (doll[i] && i % 2 === 0) pool.push(doll[i]); }
  const old = Object.keys(P.clips);
  const cuts: {t0: number; step: number}[] = [];
  for (let i = 0; i < 4; i++) cuts.push({t0: i * 0.75, step: 0.75});
  for (let i = 0; i < 8; i++) cuts.push({t0: 3 + i * 0.375, step: 0.375});
  for (let i = 0; i < 8; i++) cuts.push({t0: 6 + i * 0.1875, step: 0.1875});
  const idx = cuts.filter((c) => t >= c.t0).length;
  const games = P.tags[P.last].games;
  const wins = P.tags[P.last].wins;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      {cuts.map((c, j) => {
        let cref: ClipRef; let start: number;
        if (pool.length) {
          const name = pool[(j * 3) % pool.length];
          const m = s[name];
          cref = shotRef(P, name) as ClipRef;
          const base = m.hits && m.hits.length ? Math.max(0, m.hits[(j >> 1) % m.hits.length] - 0.5) : 1 + ((j * 1.9) % Math.max(1, m.dur - 3));
          start = Math.max(0, Math.min(base, m.dur - c.step - 0.3));
        } else {
          cref = P.clips[old[j % old.length]]; start = 8 + (j % 5) * 3;
        }
        return (
          <At key={j} from={c.t0} dur={c.step + 0.02}>
            <Dark c={cref} start={start} dur={c.step + 0.02} dim={1} push={[1.04 + (j % 3) * 0.02, 1.16]} drift={[(j % 2 ? 1 : -1) * 20, 0]} grade={1.4} />
          </At>
        );
      })}
      <div style={{position: 'absolute', right: 60, top: 40}}><Clock ticks={idx} /></div>
      <div style={{position: 'absolute', left: 70, bottom: 50, fontFamily: K.mono, fontSize: 30, letterSpacing: '0.22em', color: K.text, textShadow: '0 2px 18px #000'}}>
        {`GAMES ${String(Math.round(games * clamp(t / 7.5))).padStart(2, '0')} / ${games}`}
      </div>
      <div style={{position: 'absolute', right: 70, bottom: 50, fontFamily: K.mono, fontSize: 30, letterSpacing: '0.22em', color: '#ff6a55', textShadow: '0 2px 18px #000'}}>{`WINS ${wins}`}</div>
      <AbsoluteFill style={{background: '#000', opacity: Math.max(0, 0.5 - ((t * 5.333) % 1)) * 0.22 * (t / 7.5)}} />
    </AbsoluteFill>
  );
};

// ---------------- 75 - 81 s: the biggest hit, then the tagline ----------------
const Finale: React.FC<{P: P}> = ({P}) => {
  const t = useT();
  const w = P.tags[P.last].wins;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      {t < 3 && (
        <>
          <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 50%, rgba(150,35,25,0.6), rgba(0,0,0,0) 62%)', opacity: ease(t / 0.6)}} />
          <Flash at={0} strength={1} dur={0.8} />
          <Flash at={1.5} strength={1} dur={0.8} />
          <div style={{position: 'absolute', left: 0, right: 0, top: 20}}><AbsoluteFill style={{alignItems: 'center'}}><Hit at={0} size={330} tint="red" flare={1.6} y="30%">{`${w} wins.`}</Hit></AbsoluteFill></div>
          <div style={{position: 'absolute', left: 0, right: 0, top: 330}}><AbsoluteFill style={{alignItems: 'center'}}><Hit at={1.5} size={440} flare={1.8} y="62%">Ever.</Hit></AbsoluteFill></div>
        </>
      )}
      {t >= 3 && (
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', gap: 18, transform: `scale(${lerp(1.0, 1.06, ease((t - 3) / 3))})`}}>
          <Hit at={3.2} size={200} tint="gold" flare={0.5}>{`${w} wins. Ever.`}</Hit>
          <Small at={4.4} size={26} serif={false} track={0.5} color={K.muted}>VPT Arena</Small>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

// ---------------- 81 - 90 s: end card ----------------
const End: React.FC<{P: P}> = ({P}) => {
  const t = useT();
  const img = P.liveFrame || P.liveShot;
  const fade = 1 - ease((t - 7.4) / 1.6);
  return (
    <AbsoluteFill style={{background: '#000', opacity: fade}}>
      {hasShot(P, 'dolly4k-duels_sword') && <Shot c={shotRef(P, 'dolly4k-duels_sword') as ClipRef} start={0.4} dur={9} blur={[10, 20]} dim={0.4} push={[1.04, 1.14]} drift={[0, -50]} fadeIn={1.5} filter={HEAVY} grade={1.3} />}
      <div style={{position: 'absolute', left: 110, top: 150, width: 800}}>
        <Hit at={0.3} size={200} flare={1} y="30%" style={{textAlign: 'left'}}>VPT Arena</Hit>
        <Small at={2.4} size={64} track={0.04} style={{textAlign: 'left', marginTop: 26, lineHeight: 1.05}} italic>Watch it learn live.</Small>
        <Small at={4.0} size={28} serif={false} track={0.22} color={K.amber} style={{textAlign: 'left', marginTop: 28}}>vpt-arena.vercel.app</Small>
      </div>
      {img && t > 4.8 && (
        <div style={{position: 'absolute', left: 960, top: 150, width: 880, height: 495, opacity: ease((t - 4.8) / 1.2), boxShadow: '0 40px 100px rgba(0,0,0,0.85)', border: '1px solid rgba(233,228,216,0.35)', overflow: 'hidden', transform: `scale(${lerp(1, 1.04, ease((t - 4.8) / 4))})`}}>
          <Img src={staticFile(img)} style={{width: '100%', height: '100%', objectFit: 'cover', filter: 'contrast(1.1) saturate(0.95)'}} />
        </div>
      )}
    </AbsoluteFill>
  );
};

export const TheatMain: React.FC<any> = (P) => {
  const f = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const t = f / fps;
  let amp = 0;
  for (const h of SHAKES) if (t >= h.t) amp += h.a * Math.exp(-(t - h.t) * 7.5);
  const dx = (random(`sx${f}`) - 0.5) * 2 * amp;
  const dy = (random(`sy${f}`) - 0.5) * 2 * amp * 0.6;
  const rot = (random(`sr${f}`) - 0.5) * 2 * amp * 0.012;
  const top = (height - H) / 2;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <div style={{position: 'absolute', left: 0, top, width: W, height: H, overflow: 'hidden', background: '#000'}}>
        <div style={{position: 'absolute', inset: 0, transform: `translate(${dx}px, ${dy}px) rotate(${rot}deg) scale(${amp > 0.5 ? 1.04 : 1})`}}>
          <At from={0} dur={12}><Open P={P} /></At>
          <At from={12} dur={8.25}><Cards P={P} /></At>
          <At from={24} dur={3}><Zero P={P} /></At>
          <At from={27} dur={9}><Fought P={P} /></At>
          <At from={36} dur={18}><Hero P={P} /></At>
          <At from={54} dur={3}><Quotes P={P} /></At>
          <At from={57} dur={5.25}><Boast P={P} /></At>
          <At from={64.5} dur={1.5}><BoastTail /></At>
          <At from={66} dur={7.5}><Montage P={P} /></At>
          <At from={75} dur={6}><Finale P={P} /></At>
          <At from={81} dur={9}><End P={P} /></At>
        </div>
        <Furniture />
      </div>
    </AbsoluteFill>
  );
};

// "It still lost all of them." on black, after the silence (64.5 - 66 s)
const BoastTail: React.FC = () => (
  <AbsoluteFill style={{background: '#000'}}>
    <Center><Small at={0.15} size={66} track={0.14}>It still lost all of them.</Small></Center>
  </AbsoluteFill>
);
