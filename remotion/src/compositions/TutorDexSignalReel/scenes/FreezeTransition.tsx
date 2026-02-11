import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {SceneFrame} from '../components/SceneFrame';

const METRICS = ['127 new messages.', '4 duplicates.', '3 ghosted agencies.', '0 clarity.'];

type FreezeTransitionProps = {
  durationInFrames: number;
};

export const FreezeTransition: React.FC<FreezeTransitionProps> = ({durationInFrames}) => {
  const frame = useCurrentFrame();
  const blur = interpolate(frame, [0, durationInFrames], [0, 20], {
    extrapolateRight: 'clamp',
  });
  const wipe = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateRight: 'clamp',
  });
  const wipeInset = Math.max(0, 100 - wipe * 100);
  const lineOpacity = interpolate(frame, [6, 20], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <SceneFrame className="overflow-hidden">
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(900px 700px at 20% 15%, rgba(37,99,235,0.35) 0%, rgba(79,70,229,0.2) 40%, rgba(5,11,26,1) 100%)',
          filter: `blur(${blur}px)`,
        }}
      >
        <div className="absolute inset-0 bg-black/50" />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="space-y-3 text-center">
            {METRICS.map((line) => (
              <div key={line} className="text-4xl font-bold tracking-tight text-white">
                {line}
              </div>
            ))}
            <div className="mt-8 text-2xl font-semibold text-white/80" style={{opacity: lineOpacity}}>
              why does this feel like a full-time job?
            </div>
          </div>
        </div>
      </AbsoluteFill>

      <AbsoluteFill
        className="bg-background"
        style={{
          clipPath: `inset(0 ${wipeInset}% 0 0)`,
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600/15 via-transparent to-indigo-600/20" />
      </AbsoluteFill>
    </SceneFrame>
  );
};
