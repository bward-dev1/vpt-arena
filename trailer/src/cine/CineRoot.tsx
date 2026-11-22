import React from 'react';
import {Audio, Composition, staticFile, AbsoluteFill} from 'remotion';
import {CineMain} from './scenes';
import {TheatMain} from './theatrical';

const DEFAULT: any = {tags: {}, rounds: [], clips: {}, names: {}, improved: [], first: '', last: ''};
const WithAudio: React.FC<any> = (P) => (
  <AbsoluteFill style={{background: '#000'}}>
    <Audio src={staticFile('cinematic.mp3')} />
    <CineMain {...P} />
  </AbsoluteFill>
);

const TheatWithAudio: React.FC<any> = (P) => (
  <AbsoluteFill style={{background: '#000'}}>
    <Audio src={staticFile('theatrical.mp3')} />
    <TheatMain {...P} />
  </AbsoluteFill>
);

export const CineRoot: React.FC = () => (
  <>
    <Composition id="Cine30" component={WithAudio} width={1920} height={1080} fps={30} durationInFrames={2880} defaultProps={DEFAULT} />
    <Composition id="Cine60" component={WithAudio} width={1920} height={1080} fps={60} durationInFrames={5760} defaultProps={DEFAULT} />
    <Composition id="Theat30" component={TheatWithAudio} width={1920} height={1080} fps={30} durationInFrames={2700} defaultProps={DEFAULT} />
    <Composition id="Theat60" component={TheatWithAudio} width={1920} height={1080} fps={60} durationInFrames={5400} defaultProps={DEFAULT} />
  </>
);
