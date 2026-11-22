import React from 'react';
import {AbsoluteFill, Img, staticFile, useVideoConfig} from 'remotion';
import {At, ClipRef, Footage, Furniture, Grade, H, K, Line, Shot, W, clamp, ease, lerp, minus, useT} from './base';

type P = any;
const clipOf = (P: P, tag: string, mode: string): ClipRef => P.clips[`${tag}/${mode}`] || P.clips[`baseline/${mode}`] || Object.values(P.clips)[0];
const nm = (P: P, m: string) => P.names[m] || m.replace(/_/g, ' ');
const tagLabel = (t: string) => t.replace('-', ' ').toUpperCase();

const Caption: React.FC<{at: number; children: React.ReactNode; left?: number | string; bottom?: number; align?: 'left' | 'right'}> = ({at, children, left = 70, bottom = 54, align = 'left'}) => (
  <div style={{position: 'absolute', [align === 'left' ? 'left' : 'right']: left, bottom}}>
    <Line at={at} mono size={21} track={0.16} color={K.text} align={align} style={{opacity: 0.85}}>{children}</Line>
  </div>
);

const Divider: React.FC = () => (
  <div style={{position: 'absolute', left: W / 2 - 1, top: 0, width: 2, height: H, background: `linear-gradient(0deg, transparent, ${K.amber}, transparent)`, opacity: 0.8}} />
);

// A side-by-side of two policies in the same mode: left tag, right tag.
const Versus: React.FC<{P: P; a: string; b: string; mode: string; start: number; dur: number; ramp?: any; labelA?: string; labelB?: string}> = ({P, a, b, mode, start, dur, ramp, labelA, labelB}) => {
  const ra = P.tags[a].per[mode].return;
  const rb = P.tags[b].per[mode].return;
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', left: 0, top: 0, width: W / 2, height: H, overflow: 'hidden'}}>
        <Shot c={clipOf(P, a, mode)} start={start} dur={dur} ramp={ramp} push={[1.04, 1.12]} drift={[0, -20]} />
      </div>
      <div style={{position: 'absolute', left: W / 2, top: 0, width: W / 2, height: H, overflow: 'hidden'}}>
        <Shot c={clipOf(P, b, mode)} start={start} dur={dur} ramp={ramp} push={[1.04, 1.12]} drift={[0, 20]} />
      </div>
      <Divider />
      <div style={{position: 'absolute', left: 70, top: 56}}>
        <Line at={0.6} mono size={22} track={0.18} align="left">{labelA || tagLabel(a)}</Line>
        <Line at={0.9} mono size={18} track={0.12} color={K.muted} align="left">{nm(P, mode)} / return {minus(ra, 1)}</Line>
      </div>
      <div style={{position: 'absolute', right: 70, top: 56, textAlign: 'right'}}>
        <Line at={0.8} mono size={22} track={0.18} align="left" color={K.amber}>{labelB || tagLabel(b)}</Line>
        <Line at={1.1} mono size={18} track={0.12} color={K.muted} align="left">{nm(P, mode)} / return {minus(rb, 1)}</Line>
      </div>
    </AbsoluteFill>
  );
};

// Mean return per round, drawn slowly. `p` 0..1 is how much of the line is drawn.
const Chart: React.FC<{P: P; p: number; big?: boolean}> = ({P, p, big}) => {
  const rs: string[] = P.rounds;
  const v = rs.map((r) => P.tags[r].mean);
  const lo = Math.min(...v) - 0.4;
  const hi = Math.max(...v) + 0.4;
  const w = big ? 1300 : 1500;
  const h = big ? 360 : 150;
  const x = (i: number) => (i / (rs.length - 1)) * w;
  const y = (val: number) => h - ((val - lo) / (hi - lo)) * h;
  const pts = v.map((val, i) => [x(i), y(val)]);
  const total = pts.length - 1;
  const seg = clamp(p) * total;
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i <= total; i++) {
    const f = clamp(seg - (i - 1));
    if (f <= 0) break;
    d += ` L ${lerp(pts[i - 1][0], pts[i][0], f)} ${lerp(pts[i - 1][1], pts[i][1], f)}`;
  }
  return (
    <svg width={w + 160} height={h + 90} viewBox={`-80 -30 ${w + 160} ${h + 90}`} style={{overflow: 'visible'}}>
      {[0, 0.5, 1].map((g) => <line key={g} x1={0} x2={w} y1={h * g} y2={h * g} stroke="rgba(233,228,216,0.14)" />)}
      <path d={d} fill="none" stroke={K.amber} strokeWidth={big ? 4 : 3} strokeLinecap="round" strokeLinejoin="round" style={{filter: `drop-shadow(0 0 10px ${K.amber})`}} />
      {pts.map(([px, py], i) => (seg >= i - 0.02 ? (
        <g key={i}>
          <circle cx={px} cy={py} r={big ? 9 : 6} fill={K.ink} stroke={K.amber} strokeWidth={3} />
          <text x={px} y={py - 20} textAnchor="middle" fontFamily={K.mono} fontSize={big ? 24 : 18} fill={K.text}>{minus(v[i])}</text>
          <text x={px} y={h + 40} textAnchor="middle" fontFamily={K.mono} fontSize={big ? 20 : 15} fill={K.muted} letterSpacing="2">{tagLabel(rs[i])}</text>
        </g>
      ) : null))}
    </svg>
  );
};

// ---------------- 1. Cold open (0 - 12.8 s) ----------------
const ColdOpen: React.FC<{P: P}> = ({P}) => {
  const a = P.tags[P.last];
  const allZero = Object.values(P.tags).every((x: any) => x.wins === 0);
  const dur = 8.8;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <Line at={1.2} until={3.6} size={54} track={0.06} style={{position: 'absolute', left: 0, right: 0, top: H / 2 - 36}}>
        {allZero ? 'It has never won a game.' : `It has won ${a.wins} of ${a.games} games.`}
      </Line>
      <At from={4.0} dur={dur}>
        <Shot c={clipOf(P, 'baseline', 'duels_sword')} start={6} dur={dur} fadeIn={1.4} push={[1.02, 1.16]} drift={[10, -30]}
          ramp={[{at: 0, rate: 1}, {at: 2.6, rate: 1}, {at: 3.9, rate: 0.3}, {at: 6.1, rate: 0.3}, {at: 7.5, rate: 1}]} />
        <Caption at={1.6}>{`baseline / ${nm(P, 'duels_sword')} / ${P.tags.baseline.per.duels_sword ? Math.round(P.tags.baseline.per.duels_sword.win_rate * P.tags.baseline.per.duels_sword.episodes) : 0} of ${P.tags.baseline.per.duels_sword?.episodes ?? 3} wins`}</Caption>
      </At>
    </AbsoluteFill>
  );
};

// ---------------- 2. The premise (12.8 - 32 s) ----------------
const Premise: React.FC<{P: P}> = ({P}) => {
  const n = Object.keys(P.tags[P.last].per).length;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <At from={0} dur={6.4}>
        <Shot c={clipOf(P, 'baseline', 'the_bridge')} start={9} dur={6.4} blur={[16, 7]} dim={0.55} push={[1.08, 1.16]} drift={[0, -40]} />
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', gap: 18}}>
          <Line at={0.8} size={150} track={0.02}>One network.</Line>
          <Line at={3.0} size={46} italic track={0.04} color={K.amber}>{`${n} ways to fight.`}</Line>
        </AbsoluteFill>
      </At>
      <At from={6.4} dur={6.4}>
        <Shot c={clipOf(P, 'baseline', 'bedwars_squads')} start={5} dur={6.4} blur={10} dim={0.4} push={[1.12, 1.2]} drift={[40, -60]} />
        <div style={{position: 'absolute', left: 250, top: 120, width: 1000, height: 562, overflow: 'hidden', boxShadow: '0 30px 80px rgba(0,0,0,0.7)'}}>
          <Shot c={clipOf(P, 'baseline', 'skywars_solo')} start={4} dur={6.4} push={[1.0, 1.1]} drift={[30, -30]} />
        </div>
        <div style={{position: 'absolute', right: 110, bottom: 130, width: 560}}>
          <Line at={1.0} size={52} align="left" track={0.02}>Built on OpenAI's VPT.</Line>
          <Line at={2.2} mono size={17} track={0.14} color={K.muted} align="left" style={{marginTop: 18, lineHeight: 1.7}}>Video PreTraining: a foundation model that learned Minecraft from video.</Line>
        </div>
      </At>
      <At from={12.8} dur={6.4}>
        <Shot c={clipOf(P, 'baseline', 'kitpvp')} start={8} dur={6.4} push={[1.02, 1.14]} drift={[-10, 20]} ramp={[{at: 0, rate: 1}, {at: 3.0, rate: 1}, {at: 4.2, rate: 0.35}, {at: 5.6, rate: 0.6}]} />
        <div style={{position: 'absolute', left: 90, bottom: 110}}>
          <Line at={0.8} size={50} align="left">It sees 128 x 128 pixels.</Line>
          <Line at={3.0} size={50} align="left" italic color={K.amber} style={{marginTop: 8}}>It presses keys twenty times a second.</Line>
        </div>
      </At>
    </AbsoluteFill>
  );
};

// ---------------- 3. Learning (32 - 60.8 s) ----------------
const Learning: React.FC<{P: P}> = ({P}) => {
  const t = useT();
  const [mA, mB] = P.improved;
  const first = P.first;
  const last = P.last;
  const meanF = P.tags[first].mean;
  const meanL = P.tags[last].mean;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <At from={0} dur={4.8}>
        <Shot c={clipOf(P, first, mA)} start={10} dur={4.8} blur={[18, 6]} dim={0.5} push={[1.1, 1.16]} />
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', gap: 20}}>
          <Line at={0.4} size={120} track={0.03}>Round by round.</Line>
          <Line at={1.6} mono size={20} track={0.2} color={K.muted}>12 cloud workers a round / merged by federated averaging</Line>
        </AbsoluteFill>
      </At>
      <At from={4.8} dur={8}>
        <Versus P={P} a={first} b={last} mode={mA} start={12} dur={8} ramp={[{at: 0, rate: 1}, {at: 3, rate: 1}, {at: 4.2, rate: 0.4}, {at: 6, rate: 1}]} />
      </At>
      <At from={12.8} dur={8}>
        <Versus P={P} a={first} b={last} mode={mB} start={12} dur={8} ramp={[{at: 0, rate: 1}, {at: 4, rate: 1}, {at: 5, rate: 0.4}, {at: 7, rate: 1}]} />
      </At>
      {t >= 4.8 && t < 20.8 && (
        <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 270, background: 'linear-gradient(0deg, rgba(0,0,0,0.78), rgba(0,0,0,0))'}}>
          <div style={{position: 'absolute', left: 170, bottom: 40}}><Chart P={P} p={ease((t - 5.4) / 14)} /></div>
          <div style={{position: 'absolute', left: 70, top: 20, fontFamily: K.mono, fontSize: 16, letterSpacing: 3, color: K.muted}}>MEAN RETURN</div>
        </div>
      )}
      <At from={20.8} dur={8}>
        <Shot c={clipOf(P, last, mB)} start={20} dur={8} blur={18} dim={0.3} push={[1.1, 1.16]} />
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'flex-start', paddingTop: 80}}>
          <Line at={0.4} size={84} track={0.03}>{`${minus(meanF)}  →  ${minus(meanL)}`}</Line>
          <Line at={1.4} mono size={19} track={0.2} color={K.muted} style={{marginTop: 8}}>{`mean return over ${Object.keys(P.tags[last].per).length} modes, ${tagLabel(first)} to ${tagLabel(last)}`}</Line>
        </AbsoluteFill>
        <div style={{position: 'absolute', left: 260, bottom: 40}}><Chart P={P} big p={ease((t - 21.2) / 5)} /></div>
      </At>
    </AbsoluteFill>
  );
};

// ---------------- 4. The rivals (60.8 - 76.8 s) ----------------
const Rivals: React.FC<{P: P}> = ({P}) => {
  const t = useT();
  const last = P.last;
  const rows = [
    {k: 'baseline', label: 'VPT baseline'}, {k: P.scratch, label: 'Trained from scratch'}, {k: P.rival, label: "OpenAI's final model"}, {k: last, label: tagLabel(last)},
  ].filter((r) => r.k && P.tags[r.k]);
  const lo = Math.min(...rows.map((r) => P.tags[r.k].mean)) - 0.3;
  const hi = Math.max(...rows.map((r) => P.tags[r.k].mean)) + 0.3;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <At from={0} dur={8}>
        <Versus P={P} a={P.rival} b={last} mode="duels_sword" start={14} dur={8} labelA="OPENAI'S FINAL RELEASED MODEL" labelB={tagLabel(last)}
          ramp={[{at: 0, rate: 1}, {at: 3.2, rate: 1}, {at: 4.4, rate: 0.35}, {at: 6.4, rate: 0.8}]} />
        <div style={{position: 'absolute', left: 0, right: 0, bottom: 60, textAlign: 'center'}}>
          <Line at={1.2} mono size={20} track={0.18} color={K.muted}>{`mean return ${minus(P.tags[P.rival].mean)} vs ${minus(P.tags[last].mean)}`}</Line>
          <Line at={3.0} size={54} track={0.02} style={{marginTop: 10}}>{`${tagLabel(last).replace('ROUND', 'Round').toLowerCase().replace('round', 'Round')} scores higher in ${P.duelsBeaten} of ${P.duelsTotal} duels.`}</Line>
        </div>
      </At>
      {P.scratch && (
        <At from={8} dur={4.8}>
          <Versus P={P} a={P.scratch} b={last} mode="duels_classic" start={16} dur={4.8} labelA="TRAINED FROM SCRATCH" labelB={tagLabel(last)} ramp={[{at: 0, rate: 1}, {at: 2, rate: 0.45}, {at: 3.6, rate: 1}]} />
          <div style={{position: 'absolute', left: 0, right: 0, bottom: 60, textAlign: 'center'}}>
            <Line at={1.0} size={60} italic track={0.02}>{`Left behind. ${minus(P.tags[P.scratch].mean)}`}</Line>
          </div>
        </At>
      )}
      <At from={12.8} dur={3.2}>
        <Shot c={clipOf(P, last, 'duels_sword')} start={24} dur={3.2} blur={20} dim={0.25} push={[1.1, 1.14]} />
        <div style={{position: 'absolute', left: 340, top: 150, width: 1240}}>
          {rows.map((r, i) => {
            const v = P.tags[r.k].mean;
            const f = ease((t - 12.8 - 0.25 - i * 0.18) / 0.9);
            const wBar = ((v - lo) / (hi - lo)) * 820 * f;
            const mine = r.k === last;
            return (
              <div key={r.k} style={{display: 'flex', alignItems: 'center', gap: 24, marginBottom: 46, opacity: clamp(f * 3)}}>
                <div style={{width: 330, textAlign: 'right', fontFamily: K.serif, fontSize: 34, color: mine ? K.amber : K.text}}>{r.label}</div>
                <div style={{height: 20, width: Math.max(4, wBar), background: mine ? K.amber : 'rgba(233,228,216,0.5)', boxShadow: mine ? `0 0 24px ${K.amber}` : undefined}} />
                <div style={{fontFamily: K.mono, fontSize: 28, color: K.text}}>{minus(v)}</div>
              </div>
            );
          })}
        </div>
      </At>
    </AbsoluteFill>
  );
};

// ---------------- 5. The honest beat and the live card (76.8 - 96 s) ----------------
const Honest: React.FC<{P: P}> = ({P}) => {
  const t = useT();
  const wins = P.tags[P.last].wins;
  const img = P.liveFrame || P.liveShot;
  const fadeOut = 1 - ease((t - 17.6) / 1.6);
  return (
    <AbsoluteFill style={{background: '#000'}}>
      {t < 6.4 && (
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', gap: 10}}>
          <Line at={0.6} until={undefined} size={150} track={0.04}>{`${wins} wins.`}</Line>
          {wins === 0 && <Line at={3.5} size={150} italic color={K.amber} track={0.04}>Yet.</Line>}
        </AbsoluteFill>
      )}
      {t >= 6.4 && (
        <AbsoluteFill style={{opacity: fadeOut}}>
          {img && (
            <AbsoluteFill style={{overflow: 'hidden'}}>
              <AbsoluteFill style={{transform: `scale(${lerp(1.15, 1.3, ease((t - 6.4) / 12.8))})`, filter: 'blur(26px)', opacity: ease((t - 6.4) / 2) * 0.5}}>
                <Img src={staticFile(img)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
                <Grade />
              </AbsoluteFill>
            </AbsoluteFill>
          )}
          <div style={{position: 'absolute', left: 120, top: 190, width: 800}}>
            <Line at={7.2} size={104} align="left" track={0.02} style={{lineHeight: 1.02}}>Watch it learn live.</Line>
            <Line at={9.6} mono size={26} align="left" track={0.2} color={K.amber} style={{marginTop: 34}}>vpt-arena.vercel.app</Line>
            <Line at={10.6} mono size={16} align="left" track={0.16} color={K.muted} style={{marginTop: 14}}>live stream / live training / simulation lab</Line>
          </div>
          {img && t > 11.4 && (
            <div style={{position: 'absolute', left: 960, top: 128, width: 880, height: 495, opacity: ease((t - 11.4) / 1.6), transform: `translateY(${(1 - ease((t - 11.4) / 1.6)) * 24}px) scale(${lerp(1, 1.04, ease((t - 11.4) / 7))})`, boxShadow: '0 40px 100px rgba(0,0,0,0.8)', overflow: 'hidden', border: '1px solid rgba(233,228,216,0.25)'}}>
              <Img src={staticFile(img)} style={{width: '100%', height: '100%', objectFit: 'cover', filter: 'contrast(1.08) saturate(0.9)'}} />
              <Grade strength={0.8} />
            </div>
          )}
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

export const CineMain: React.FC<any> = (P) => {
  const {height} = useVideoConfig();
  const top = (height - H) / 2;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <div style={{position: 'absolute', left: 0, top, width: W, height: H, overflow: 'hidden', background: '#000'}}>
        <At from={0} dur={12.8}><ColdOpen P={P} /></At>
        <At from={12.8} dur={19.2}><Premise P={P} /></At>
        <At from={32} dur={28.8}><Learning P={P} /></At>
        <At from={60.8} dur={16}><Rivals P={P} /></At>
        <At from={76.8} dur={19.2}><Honest P={P} /></At>
        <Furniture />
      </div>
    </AbsoluteFill>
  );
};
