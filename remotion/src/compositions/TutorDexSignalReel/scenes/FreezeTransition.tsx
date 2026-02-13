import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {SceneFrame} from '../components/SceneFrame';
import {TelegramFeed} from '../components/TelegramFeed';

type FreezeTransitionProps = {
  durationInFrames: number;
};

export const FreezeTransition: React.FC<FreezeTransitionProps> = ({durationInFrames}) => {
  const frame = useCurrentFrame();
  const blur = interpolate(frame, [0, durationInFrames], [3, 12], {
    extrapolateRight: 'clamp',
  });
  const cleanOpacity = interpolate(frame, [8, durationInFrames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const lineOpacity = interpolate(frame, [6, 20], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <SceneFrame className="overflow-hidden">
      <AbsoluteFill
        style={{
          background: 'linear-gradient(180deg, #04070f 0%, #050b1a 100%)',
        }}
      >
        <div className="absolute inset-0 bg-black/50" />
        <TelegramFeed scrollY={-260} blur={blur} opacity={1} />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="mt-44 text-2xl font-semibold text-white/80" style={{opacity: lineOpacity}}>
            why does this feel like a full-time job?
          </div>
        </div>
      </AbsoluteFill>

      <AbsoluteFill
        style={{
          opacity: cleanOpacity,
        }}
      >
        <div className="absolute inset-0 bg-background" />
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600/10 via-transparent to-indigo-600/10" />
      </AbsoluteFill>
    </SceneFrame>
  );
};
