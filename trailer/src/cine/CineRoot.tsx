import React from 'react';
import {Audio, Composition, staticFile, AbsoluteFill} from 'remotion';
import {CineMain} from './scenes';

const DEFAULT: any = {tags: {}, rounds: [], clips: {}, names: {}, improved: [], first: '', last: ''};
const WithAudio: React.FC<any> = (P) => (
  <AbsoluteFill style={{background: '#000'}}>
    <Audio src={staticFile('cinematic.mp3')} />
    <CineMain {...P} />
  </AbsoluteFill>
);

export const CineRoot: React.FC = () => (
  <>
    <Composition id="Cine30" component={WithAudio} width={1920} height={1080} fps={30} durationInFrames={2880} defaultProps={DEFAULT} />
    <Composition id="Cine60" component={WithAudio} width={1920} height={1080} fps={60} durationInFrames={5760} defaultProps={DEFAULT} />
  </>
);
