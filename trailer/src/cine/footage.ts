import {ClipRef} from './base';

// Footage lookups: the HD shoot (release `footage`) when it is there, the old 480x270 eval clips as the fallback.
export const tagKey = (P: any, tag: string) => (tag === P.first ? 'r0' : tag === P.last ? 'r4' : tag === 'openai-rl-2x' ? 'openai' : String(tag).startsWith('scratch') ? 'scratch' : tag);
export const shotName = (P: any, tag: string, mode: string) => `${tagKey(P, tag)}-${mode}`;
export const shotRef = (P: any, name: string): ClipRef | undefined => (P.shots && P.shots[name] ? {clip: P.shots[name].file, clip60: P.shots[name].file, dur: P.shots[name].dur} : undefined);
export const clipFor = (P: any, tag: string, mode: string): ClipRef =>
  shotRef(P, shotName(P, tag, mode)) || P.clips[`${tag}/${mode}`] || P.clips[`baseline/${mode}`] || (Object.values(P.clips)[0] as ClipRef);
export const hasShot = (P: any, name: string) => !!(P.shots && P.shots[name]);
// Where to start a window of `len` seconds: a second and a half before the first damage dealt, else before the end of a short episode, else early.
export const startFor = (P: any, name: string, len: number, fallback = 12) => {
  const m = P.shots && P.shots[name];
  if (!m) return fallback;
  let s = m.hits && m.hits.length ? m.hits[0] - 1.5 : m.endT ? m.endT - len - 0.5 : 1.5;
  return Math.max(0, Math.min(s, Math.max(0, m.dur - len - 0.3)));
};
// A window ending at the episode's end (the fall, the finish)
export const endWindow = (P: any, name: string, len: number) => {
  const m = P.shots && P.shots[name];
  if (!m) return 12;
  return Math.max(0, m.dur - len - 0.2);
};
