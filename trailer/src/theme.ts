import {loadFont as loadHead} from '@remotion/google-fonts/SpaceGrotesk';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';

const head = loadHead('normal', {weights: ['500', '700'], subsets: ['latin']});
const mono = loadMono('normal', {weights: ['500', '700'], subsets: ['latin']});

// Music clock: 128 BPM. One beat = 0.46875 s, one bar = 1.875 s, 40 bars = 75 s.
export const BPM = 128;
export const BEAT = 60 / BPM;
export const BAR = BEAT * 4;

// Colours are the dashboard's own tokens (style.css), plus one brighter glow of the accent.
export const C = {
  bg: '#080b0f',
  panel: '#121720',
  line: '#232b38',
  text: '#e8ecf2',
  muted: '#9aa5b5',
  accent: '#7cc4a0',
  glow: '#b8ffd9',
  blue: '#7ea8f0',
  warn: '#e3b65a',
  bad: '#ec7b7b',
};
export const F = {head: head.fontFamily, mono: mono.fontFamily};
