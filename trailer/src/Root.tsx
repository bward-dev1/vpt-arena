import React from 'react';
import {AbsoluteFill, Audio, Composition, staticFile} from 'remotion';
import {BAR} from './theme';
import {At} from './components';
import {Intro, Pipeline, Sees} from './scenes1';
import {Build, Cloud, Dash, Drop, Finale} from './scenes2';

const DEFAULT: any = {
  modes: [], stats: {games: 69, wins: 0, steps: 0, rounds: [], workers: []}, shots: {}, liveFrame: null,
};

const Wide: React.FC<any> = (P) => (
  <AbsoluteFill style={{background: '#080b0f'}}>
    <Audio src={staticFile('music-main.wav')} />
    <At from={0} dur={4 * BAR}><Intro P={P} /></At>
    <At from={4 * BAR} dur={4 * BAR}><Sees P={P} /></At>
    <At from={8 * BAR} dur={4 * BAR}><Pipeline P={P} /></At>
    <At from={12 * BAR} dur={8 * BAR}><Build P={P} dur={8 * BAR} /></At>
    <At from={20 * BAR} dur={8 * BAR}><Drop P={P} dur={8 * BAR} /></At>
    <At from={28 * BAR} dur={4 * BAR}><Cloud P={P} /></At>
    <At from={32 * BAR} dur={4 * BAR}><Dash P={P} /></At>
    <At from={36 * BAR} dur={4 * BAR}><Finale P={P} dur={4 * BAR} /></At>
  </AbsoluteFill>
);

const Tall: React.FC<any> = (P) => (
  <AbsoluteFill style={{background: '#080b0f'}}>
    <Audio src={staticFile('music-vertical.wav')} />
    <At from={0} dur={2 * BAR}><Intro P={P} /></At>
    <At from={2 * BAR} dur={4 * BAR}><Sees P={P} /></At>
    <At from={6 * BAR} dur={2 * BAR}><Build P={P} dur={2 * BAR} /></At>
    <At from={8 * BAR} dur={4 * BAR}><Drop P={P} dur={4 * BAR} /></At>
    <At from={12 * BAR} dur={2 * BAR}><Cloud P={P} /></At>
    <At from={14 * BAR} dur={2 * BAR}><Finale P={P} dur={2 * BAR} /></At>
  </AbsoluteFill>
);

export const Root: React.FC = () => (
  <>
    <Composition id="Main30" component={Wide} width={1920} height={1080} fps={30} durationInFrames={2250} defaultProps={DEFAULT} />
    <Composition id="Main60" component={Wide} width={1920} height={1080} fps={60} durationInFrames={4500} defaultProps={DEFAULT} />
    <Composition id="Vertical" component={Tall} width={1080} height={1920} fps={30} durationInFrames={900} defaultProps={DEFAULT} />
  </>
);
