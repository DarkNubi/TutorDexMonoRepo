import React from 'react';
import {AbsoluteFill, Sequence} from 'remotion';
import {ChaosScene} from './scenes/ChaosScene';
import {FreezeTransition} from './scenes/FreezeTransition';
import {CleanIntroScene} from './scenes/CleanIntroScene';
import {ListingCardsScene} from './scenes/ListingCardsScene';
import {ApplyFlowScene} from './scenes/ApplyFlowScene';
import {PersonalisationScene} from './scenes/PersonalisationScene';
import {OutroScene} from './scenes/OutroScene';

export const TUTORDEX_SIGNAL_FPS = 30;
export const TUTORDEX_SIGNAL_DURATION = 35 * TUTORDEX_SIGNAL_FPS;

export const TutorDexSignalReel: React.FC = () => {
  return (
    <AbsoluteFill>
      {/* Scene timing matches the storyboard: 0-7s, 7-9s, 9-14s, 14-17s, 17-23s, 23-27s, 27-35s */}
      <Sequence from={0} durationInFrames={7 * TUTORDEX_SIGNAL_FPS}>
        <ChaosScene durationInFrames={7 * TUTORDEX_SIGNAL_FPS} />
      </Sequence>
      <Sequence from={7 * TUTORDEX_SIGNAL_FPS} durationInFrames={2 * TUTORDEX_SIGNAL_FPS}>
        <FreezeTransition durationInFrames={2 * TUTORDEX_SIGNAL_FPS} />
      </Sequence>
      <Sequence from={9 * TUTORDEX_SIGNAL_FPS} durationInFrames={5 * TUTORDEX_SIGNAL_FPS}>
        <CleanIntroScene durationInFrames={5 * TUTORDEX_SIGNAL_FPS} />
      </Sequence>
      <Sequence from={14 * TUTORDEX_SIGNAL_FPS} durationInFrames={3 * TUTORDEX_SIGNAL_FPS}>
        <ListingCardsScene durationInFrames={3 * TUTORDEX_SIGNAL_FPS} />
      </Sequence>
      <Sequence from={17 * TUTORDEX_SIGNAL_FPS} durationInFrames={6 * TUTORDEX_SIGNAL_FPS}>
        <ApplyFlowScene />
      </Sequence>
      <Sequence from={23 * TUTORDEX_SIGNAL_FPS} durationInFrames={4 * TUTORDEX_SIGNAL_FPS}>
        <PersonalisationScene />
      </Sequence>
      <Sequence from={27 * TUTORDEX_SIGNAL_FPS} durationInFrames={8 * TUTORDEX_SIGNAL_FPS}>
        <OutroScene />
      </Sequence>
    </AbsoluteFill>
  );
};
