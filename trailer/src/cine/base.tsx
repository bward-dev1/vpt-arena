import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont as loadSerif} from '@remotion/google-fonts/CormorantGaramond';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';

const serif = loadSerif('normal', {weights: ['500', '600'], subsets: ['latin']});
const serifI = loadSerif('italic', {weights: ['500'], subsets: ['latin']});
const mono = loadMono('normal', {weights: ['500'], subsets: ['latin']});
void serifI;

// 75 BPM, one bar = 3.2 s. Scene starts sit on bar lines (phrases), not on beats.
export const BAR = 3.2;
export const W = 1920;
export const H = 802; // 2.39:1 inside 1920x1080 -> 139 px bars top and bottom
export const K = {
  ink: '#07090b', text: '#e9e4d8', muted: '#8f9ea0', teal: '#2b8591', amber: '#e3a64f', green: '#7cc4a0',
  serif: serif.fontFamily, mono: mono.fontFamily,
};

export const useT = () => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  return f / fps;
};
export const clamp = (x: number, a = 0, b = 1) => Math.max(a, Math.min(b, x));
export const ease = (x: number) => { const c = clamp(x); return c * c * (3 - 2 * c); };
export const lerp = (a: number, b: number, x: number) => a + (b - a) * x;
export const minus = (v: number, d = 2) => (v < 0 ? '−' : '') + Math.abs(v).toFixed(d);

export const At: React.FC<{from: number; dur: number; children?: React.ReactNode}> = ({from, dur, children}) => {
  const {fps} = useVideoConfig();
  return <Sequence from={Math.round(from * fps)} durationInFrames={Math.max(1, Math.round(dur * fps))}>{children}</Sequence>;
};

export type ClipRef = {clip: string; clip60: string | null; dur: number};
export const srcOf = (c: ClipRef, fps: number) => staticFile(fps >= 50 && c.clip60 ? c.clip60 : c.clip);

type Ramp = {at: number; rate: number}[];
const rateAt = (ramp: Ramp | undefined, t: number) => {
  if (!ramp || !ramp.length) return 1;
  if (t <= ramp[0].at) return ramp[0].rate;
  for (let i = 1; i < ramp.length; i++) {
    if (t <= ramp[i].at) return lerp(ramp[i - 1].rate, ramp[i].rate, ease((t - ramp[i - 1].at) / (ramp[i].at - ramp[i - 1].at)));
  }
  return ramp[ramp.length - 1].rate;
};

// Footage with a speed ramp: the clip is cut into 0.5 s slices, each played at the ramp's rate, with the source position carried across slices.
export const Footage: React.FC<{c: ClipRef; start: number; dur: number; ramp?: Ramp; filter?: string; style?: React.CSSProperties}> = ({c, start, dur, ramp, filter, style}) => {
  const {fps} = useVideoConfig();
  const src = srcOf(c, fps);
  const slices: {t0: number; len: number; rate: number; pos: number}[] = [];
  let pos = start;
  const step = ramp ? 0.5 : dur;
  for (let t0 = 0; t0 < dur - 1e-6; t0 += step) {
    const len = Math.min(step, dur - t0);
    const rate = Math.round(rateAt(ramp, t0 + len / 2) * 50) / 50;
    const last = slices[slices.length - 1];
    if (last && last.rate === rate) last.len += len;
    else slices.push({t0, len, rate, pos});
    pos += len * rate;
  }
  return (
    <AbsoluteFill style={style}>
      {slices.map((s, i) => (
        <Sequence key={i} from={Math.round(s.t0 * fps)} durationInFrames={Math.max(1, Math.round(s.len * fps) + 1)}>
          <OffthreadVideo src={src} startFrom={Math.round(s.pos * fps)} playbackRate={s.rate} muted style={{width: '100%', height: '100%', objectFit: 'cover', filter: filter || 'contrast(1.08) saturate(0.88) brightness(0.96)'}} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

// Teal in the shadows, amber in the highlights, laid over footage.
export const Grade: React.FC<{strength?: number}> = ({strength = 1}) => (
  <>
    <AbsoluteFill style={{background: 'rgb(34,112,128)', mixBlendMode: 'soft-light', opacity: 0.6 * strength}} />
    <AbsoluteFill style={{background: 'linear-gradient(205deg, rgba(247,176,80,0.75), rgba(247,176,80,0) 58%)', mixBlendMode: 'soft-light', opacity: 0.55 * strength}} />
    <AbsoluteFill style={{background: 'linear-gradient(0deg, rgba(6,30,38,0.55), rgba(6,30,38,0) 55%)', mixBlendMode: 'multiply', opacity: strength}} />
  </>
);

// A graded shot with a slow push-in and drift. `blur` > 0 gives a soft backdrop for title cards (depth of field).
export const Shot: React.FC<{c: ClipRef; start: number; dur: number; ramp?: Ramp; push?: [number, number]; drift?: [number, number]; blur?: number | [number, number]; dim?: number; fadeIn?: number; style?: React.CSSProperties}> = ({
  c, start, dur, ramp, push = [1.04, 1.14], drift = [0, 0], blur = 0, dim = 1, fadeIn = 0, style,
}) => {
  const t = useT();
  const p = ease(t / dur);
  const b = Array.isArray(blur) ? lerp(blur[0], blur[1], ease(t / Math.min(dur, 3))) : blur;
  return (
    <AbsoluteFill style={{overflow: 'hidden', background: '#000', opacity: fadeIn ? ease(t / fadeIn) : 1, ...style}}>
      <AbsoluteFill style={{transform: `translateX(${lerp(drift[0], drift[1], p)}px) scale(${lerp(push[0], push[1], p)})`, filter: b ? `blur(${b}px)` : undefined}}>
        <Footage c={c} start={start} dur={dur} ramp={ramp} />
        <Grade />
      </AbsoluteFill>
      {dim < 1 && <AbsoluteFill style={{background: '#000', opacity: 1 - dim}} />}
    </AbsoluteFill>
  );
};

// Serif title line: rises a few pixels and focuses in, holds, then fades.
export const Line: React.FC<{children: React.ReactNode; at: number; until?: number; size?: number; track?: number; mono?: boolean; italic?: boolean; color?: string; style?: React.CSSProperties; align?: 'left' | 'center'}> = ({
  children, at, until, size = 64, track = 0.04, mono = false, italic = false, color = K.text, style, align = 'center',
}) => {
  const t = useT();
  const inn = ease((t - at) / 1.4);
  const out = until != null ? 1 - ease((t - until) / 0.8) : 1;
  if (t < at || out <= 0) return null;
  return (
    <div style={{
      fontFamily: mono ? K.mono : K.serif, fontWeight: 500, fontStyle: italic ? 'italic' : 'normal', fontSize: size, letterSpacing: `${track}em`,
      textTransform: mono ? 'uppercase' : undefined, color, textAlign: align, opacity: inn * out, transform: `translateY(${(1 - inn) * 14}px)`,
      filter: inn < 1 ? `blur(${(1 - inn) * 6}px)` : undefined, textShadow: '0 2px 24px rgba(0,0,0,0.6)', ...style,
    }}>{children}</div>
  );
};

// Frame furniture: letterbox bars, vignette, film grain. Grain cycles 8 pre-made noise frames at 12 Hz.
export const Furniture: React.FC = () => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = Math.floor((f / fps) * 12) % 8;
  return (
    <>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 52%, rgba(0,0,0,0.5) 100%)'}} />
      <AbsoluteFill style={{mixBlendMode: 'overlay', opacity: 0.15}}>
        <Img src={staticFile(`grain/g${g + 1}.png`)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      </AbsoluteFill>
    </>
  );
};
