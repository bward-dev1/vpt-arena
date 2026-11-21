import React from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, staticFile, spring, random, useCurrentFrame, useVideoConfig} from 'remotion';
import {BEAT, C, F} from './theme';

// Every animation is a function of time in seconds, so 30 fps and 60 fps renders are the same edit.
export const useT = () => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  return f / fps;
};
export const useTall = () => {
  const {width, height} = useVideoConfig();
  return height > width;
};
export const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
export const easeOut = (x: number) => 1 - Math.pow(1 - clamp01(x), 3);
export const pulse = (t: number, k = 5) => Math.exp(-(((t % BEAT) + BEAT) % BEAT / BEAT) * k);
export const fmtInt = (n: number) => Math.round(n).toLocaleString('en-US');

// Place a scene at an absolute time (seconds) in the trailer.
export const At: React.FC<{from: number; dur: number; children?: React.ReactNode}> = ({from, dur, children}) => {
  const {fps} = useVideoConfig();
  return (
    <Sequence from={Math.round(from * fps)} durationInFrames={Math.max(1, Math.round(dur * fps))}>
      {children}
    </Sequence>
  );
};

// Voxel/grid motif: square-cell grid, cells that flash on every beat, and a perspective floor.
export const VoxelBG: React.FC<{dim?: number; floor?: boolean}> = ({dim = 1, floor = true}) => {
  const t = useT();
  const {width, height} = useVideoConfig();
  const cell = 60;
  const cols = Math.ceil(width / cell);
  const rows = Math.ceil(height / cell);
  const b = Math.floor(t / BEAT);
  const lit = Array.from({length: 16}, (_, i) => ({
    x: Math.floor(random(`x${b}-${i}`) * cols),
    y: Math.floor(random(`y${b}-${i}`) * rows),
    k: 0.5 + random(`k${b}-${i}`) * 0.5,
  }));
  const p = pulse(t, 4);
  return (
    <AbsoluteFill style={{background: C.bg, overflow: 'hidden'}}>
      <AbsoluteFill
        style={{
          opacity: 0.55 * dim,
          backgroundImage: `linear-gradient(${C.line} 1px, transparent 1px), linear-gradient(90deg, ${C.line} 1px, transparent 1px)`,
          backgroundSize: `${cell}px ${cell}px`,
        }}
      />
      {lit.map((c, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            left: c.x * cell + 1,
            top: c.y * cell + 1,
            width: cell - 1,
            height: cell - 1,
            background: C.accent,
            opacity: 0.22 * p * c.k * dim,
          }}
        />
      ))}
      {floor && (
        <div
          style={{
            position: 'absolute',
            left: '-25%',
            width: '150%',
            bottom: -height * 0.18,
            height: height * 0.62,
            transform: 'perspective(520px) rotateX(64deg)',
            transformOrigin: '50% 100%',
            backgroundImage: `linear-gradient(${C.accent} 2px, transparent 2px), linear-gradient(90deg, ${C.accent} 2px, transparent 2px)`,
            backgroundSize: '90px 90px',
            backgroundPosition: `0 ${(t * 140) % 90}px`,
            opacity: 0.2 * dim,
            WebkitMaskImage: 'linear-gradient(to top, black, transparent 90%)',
            maskImage: 'linear-gradient(to top, black, transparent 90%)',
          }}
        />
      )}
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 45%, transparent 35%, rgba(0,0,0,0.75) 100%)'}} />
    </AbsoluteFill>
  );
};

// Kinetic text: slams in from large, with a spring, at time `at` (seconds, scene-local).
export const Slam: React.FC<{
  children: React.ReactNode;
  at?: number;
  size?: number;
  color?: string;
  mono?: boolean;
  glow?: boolean;
  align?: 'left' | 'center' | 'right';
  style?: React.CSSProperties;
}> = ({children, at = 0, size = 140, color = C.text, mono = false, glow = false, align = 'left', style}) => {
  const t = useT();
  const {fps} = useVideoConfig();
  if (t < at) return null;
  const p = spring({frame: Math.max(0, Math.round((t - at) * fps)), fps, config: {damping: 11, stiffness: 190, mass: 0.6}});
  const s = 1.7 - 0.7 * p;
  return (
    <div
      style={{
        fontFamily: mono ? F.mono : F.head,
        fontWeight: 700,
        fontSize: size,
        lineHeight: 0.98,
        letterSpacing: mono ? 0 : -size * 0.025,
        color,
        textTransform: 'uppercase',
        textAlign: align,
        transform: `scale(${s})`,
        transformOrigin: align === 'center' ? '50% 50%' : align === 'right' ? '100% 50%' : '0% 50%',
        opacity: clamp01((t - at) * 16),
        textShadow: glow ? `0 0 ${size * 0.35}px ${C.accent}` : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

export const Chip: React.FC<{children: React.ReactNode; color?: string; size?: number; solid?: boolean; style?: React.CSSProperties}> = ({
  children,
  color = C.accent,
  size = 22,
  solid = false,
  style,
}) => (
  <div
    style={{
      display: 'inline-block',
      fontFamily: F.mono,
      fontWeight: 700,
      fontSize: size,
      letterSpacing: 1,
      textTransform: 'uppercase',
      color: solid ? C.bg : color,
      background: solid ? color : 'rgba(8,11,15,0.78)',
      border: `2px solid ${color}`,
      padding: `${size * 0.25}px ${size * 0.6}px`,
      whiteSpace: 'nowrap',
      ...style,
    }}
  >
    {children}
  </div>
);

export const Count: React.FC<{to: number; at?: number; dur?: number; color?: string; size?: number; style?: React.CSSProperties}> = ({
  to,
  at = 0,
  dur = 1.2,
  color = C.text,
  size = 120,
  style,
}) => {
  const t = useT();
  const v = to * easeOut((t - at) / dur);
  return <span style={{fontFamily: F.mono, fontWeight: 700, fontSize: size, color, ...style}}>{fmtInt(v)}</span>;
};

export type Mode = {id: string; name: string; clip: string; dur: number; tag: string; wins: number; episodes: number; ret: number | null};

export const clipStart = (m: Mode, i: number, shown = 9) => {
  const want = 1 + ((i * 2.9) % 26);
  return Math.max(0, Math.min(want, (m.dur || 40) - shown - 1));
};

// A gameplay clip, restyled: pixel-crisp scaling, graded, green/blue duotone wash, scanlines, vignette, corner brackets, label.
export const Clip: React.FC<{
  m: Mode;
  start: number;
  label?: boolean;
  big?: boolean;
  punch?: boolean;
  style?: React.CSSProperties;
}> = ({m, start, label = true, big = false, punch = true, style}) => {
  const t = useT();
  const {fps} = useVideoConfig();
  const s = punch ? 1 + 0.035 * pulse(t, 6) : 1;
  const br = big ? 28 : 16;
  const bw = big ? 4 : 2;
  const corner = (pos: React.CSSProperties) => (
    <div style={{position: 'absolute', width: br, height: br, borderColor: C.accent, borderStyle: 'solid', borderWidth: 0, ...pos}} />
  );
  return (
    <div style={{position: 'absolute', overflow: 'hidden', background: '#000', ...style}}>
      <div style={{position: 'absolute', inset: 0, transform: `scale(${s})`}}>
        <OffthreadVideo
          src={staticFile(m.clip)}
          startFrom={Math.round(start * fps)}
          muted
          style={{width: '100%', height: '100%', objectFit: 'cover', imageRendering: 'pixelated', filter: 'contrast(1.2) saturate(1.3) brightness(0.93) hue-rotate(-6deg)'}}
        />
      </div>
      <div style={{position: 'absolute', inset: 0, background: `linear-gradient(160deg, rgba(124,196,160,0.14), rgba(8,11,15,0) 55%, rgba(126,168,240,0.1))`, mixBlendMode: 'screen'}} />
      <div style={{position: 'absolute', inset: 0, background: 'repeating-linear-gradient(0deg, rgba(0,0,0,0.26) 0px, rgba(0,0,0,0.26) 1px, transparent 1px, transparent 3px)'}} />
      <div style={{position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.5) 100%)'}} />
      <div style={{position: 'absolute', inset: 0, boxShadow: `inset 0 0 0 ${bw / 2}px rgba(124,196,160,0.45)`}} />
      {corner({left: 6, top: 6, borderLeftWidth: bw, borderTopWidth: bw})}
      {corner({right: 6, top: 6, borderRightWidth: bw, borderTopWidth: bw})}
      {corner({left: 6, bottom: 6, borderLeftWidth: bw, borderBottomWidth: bw})}
      {corner({right: 6, bottom: 6, borderRightWidth: bw, borderBottomWidth: bw})}
      {label && (
        <div style={{position: 'absolute', left: big ? 36 : 14, bottom: big ? 34 : 14, display: 'flex', gap: 10, alignItems: 'center'}}>
          <Chip size={big ? 28 : 14} solid>
            {m.name}
          </Chip>
          <Chip size={big ? 24 : 12} color={m.wins > 0 ? C.accent : C.bad}>
            {m.tag === 'baseline' ? 'baseline' : m.tag.replace('-', ' ')} {m.wins}/{m.episodes} wins
          </Chip>
        </div>
      )}
    </div>
  );
};

// White-green flash on a hit. `at` in scene-local seconds.
export const Flash: React.FC<{at: number; dur?: number; strength?: number}> = ({at, dur = 0.28, strength = 0.7}) => {
  const t = useT();
  const k = 1 - clamp01((t - at) / dur);
  if (t < at || k <= 0) return null;
  return <AbsoluteFill style={{background: C.glow, opacity: strength * k * k, mixBlendMode: 'screen'}} />;
};

export const Brand: React.FC<{size?: number}> = ({size = 30}) => (
  <div style={{display: 'flex', alignItems: 'center', gap: size * 0.4, fontFamily: F.head, fontWeight: 700, fontSize: size, color: C.text, letterSpacing: 1}}>
    <svg width={size * 1.1} height={size * 1.1} viewBox="0 0 8 8">
      {[[0, 4], [2, 2], [4, 0], [2, 4], [4, 2], [6, 4], [4, 4], [6, 2]].map(([x, y], i) => (
        <rect key={i} x={x} y={y} width="2" height="2" fill={i % 3 === 0 ? C.accent : C.glow} opacity={i % 3 === 0 ? 1 : 0.7} />
      ))}
    </svg>
    VPT ARENA
  </div>
);
