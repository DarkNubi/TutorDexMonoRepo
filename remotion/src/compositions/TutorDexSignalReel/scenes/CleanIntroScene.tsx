import React from 'react';
import {SceneFrame} from '../components/SceneFrame';
import {StaggerLines} from '../components/StaggerLines';

const HERO_LINES = ['you don’t need more listings.', 'you need signal.'];
const DETAIL_LINES = ['real listings.', 'ranked by likelihood.', 'status tracked.'];

type CleanIntroSceneProps = {
  durationInFrames: number;
};

export const CleanIntroScene: React.FC<CleanIntroSceneProps> = () => {
  return (
    <SceneFrame className="flex items-center justify-center">
      <div className="absolute inset-0 bg-gradient-to-b from-blue-600/10 via-transparent to-indigo-600/10" />
      <div className="relative z-10 max-w-4xl px-20">
        <StaggerLines
          lines={HERO_LINES}
          stagger={10}
          className="text-4xl font-semibold text-foreground"
          lineClassName="leading-tight"
        />
        <div className="mt-6">
          <StaggerLines
            lines={DETAIL_LINES}
            startFrame={30}
            stagger={10}
            className="text-3xl font-semibold text-muted-foreground"
            lineClassName="leading-tight"
          />
        </div>
      </div>
    </SceneFrame>
  );
};
