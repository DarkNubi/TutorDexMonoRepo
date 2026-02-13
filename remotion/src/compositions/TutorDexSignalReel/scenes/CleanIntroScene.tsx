import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {SceneFrame} from '../components/SceneFrame';

const HERO_LINES = ['You don’t need more listings.', 'You need signal.'];

type CleanIntroSceneProps = {
  durationInFrames: number;
};

export const CleanIntroScene: React.FC<CleanIntroSceneProps> = () => {
  const frame = useCurrentFrame();
  return (
    <SceneFrame className="flex items-center justify-center">
      <div className="absolute inset-0 bg-gradient-to-b from-blue-600/10 via-transparent to-indigo-600/10" />
      <div className="relative z-10 max-w-4xl px-20">
        {HERO_LINES.map((line, index) => {
          const start = index * 22;
          const opacity = interpolate(frame, [start, start + 12], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });
          const translateY = interpolate(frame, [start, start + 12], [10, 0], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });
          return (
            <div
              key={line}
              className="text-4xl font-semibold leading-tight text-foreground"
              style={{
                opacity,
                transform: `translateY(${translateY}px)`,
              }}
            >
              {line}
            </div>
          );
        })}
      </div>
    </SceneFrame>
  );
};
