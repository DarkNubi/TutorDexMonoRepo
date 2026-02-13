import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {SceneFrame} from '../components/SceneFrame';
import {TelegramFeed} from '../components/TelegramFeed';

type ChaosSceneProps = {
  durationInFrames: number;
};

export const ChaosScene: React.FC<ChaosSceneProps> = ({durationInFrames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const chaosStart = 0;
  const chaosEnd = 7 * fps;
  const scrollY = interpolate(frame, [chaosStart, chaosEnd], [0, -260], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const counter = Math.round(
    interpolate(frame, [0, 60], [0, 127], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    })
  );
  const clarityOpacity = interpolate(frame, [chaosEnd - 24, chaosEnd - 6], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const counterOpacity = interpolate(frame, [10, 24, chaosEnd - 36, chaosEnd - 24], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const PHRASES = ['URGENT', '$60/hr', 'already filled', 'duplicate'];
  const phraseDuration = Math.floor((chaosEnd - 30) / PHRASES.length);

  return (
    <SceneFrame
      className="overflow-hidden"
      style={{
        background: 'linear-gradient(180deg, #04070f 0%, #050b1a 100%)',
      }}
    >
      <div className="absolute inset-0 bg-black/45" />

      <TelegramFeed scrollY={scrollY} blur={3} opacity={0.95} />

      <AbsoluteFill className="flex items-center justify-center">
        <div className="text-center text-white">
          {PHRASES.map((phrase, index) => {
            const start = 18 + index * phraseDuration;
            const enter = interpolate(frame, [start, start + 8], [20, 0], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            });
            const opacity = interpolate(frame, [start, start + 8, start + 32, start + 40], [0, 1, 1, 0], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            });
            return (
              <div
                key={phrase}
                className="absolute left-1/2 top-1/2 w-[720px] -translate-x-1/2 -translate-y-1/2 text-5xl font-semibold tracking-tight"
                style={{
                  transform: `translate(-50%, calc(-50% + ${enter}px))`,
                  opacity,
                }}
              >
                {phrase}
              </div>
            );
          })}
        </div>
      </AbsoluteFill>

      <div
        className="absolute left-16 bottom-28 rounded-2xl border border-white/10 bg-white/10 px-5 py-3 text-sm font-semibold uppercase tracking-wide text-white/80"
        style={{opacity: counterOpacity, backdropFilter: 'blur(6px)'}}
      >
        {counter} new messages
      </div>

      <div
        className="absolute left-16 bottom-16 text-sm font-semibold uppercase tracking-wide text-white/60"
        style={{opacity: clarityOpacity}}
      >
        0 clarity.
      </div>
    </SceneFrame>
  );
};
