import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {SceneFrame} from '../components/SceneFrame';
import {SignalCard} from '../components/SignalCard';
import {MOTION} from '../constants';

const RULE_LINE = 'no pay-to-win. no hidden boosts. no fake urgency.';
const SIGNAL_LINE = 'real listings. ranked by likelihood. status tracked.';

const CARDS = [
  {
    subject: 'Math',
    level: 'Secondary 3',
    location: 'Online',
    rate: '$60/hr',
    source: 'Agency X',
    likelyFilled: 'Low',
    freshness: 92,
    match: 82,
  },
  {
    subject: 'Chemistry',
    level: 'JC1',
    location: 'Bishan',
    rate: '$60/hr',
    source: 'Agency X',
    likelyFilled: 'Low',
    freshness: 84,
    match: 76,
  },
  {
    subject: 'English',
    level: 'Primary 6',
    location: 'Tanjong Pagar',
    rate: '$60/hr',
    source: 'Agency X',
    likelyFilled: 'Low',
    freshness: 79,
    match: 71,
  },
];

type ListingCardsSceneProps = {
  durationInFrames: number;
};

export const ListingCardsScene: React.FC<ListingCardsSceneProps> = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const signalOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const ruleOpacity = interpolate(frame, [36, 54], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <SceneFrame className="px-16 py-20">
      <div className="absolute inset-0 bg-gradient-to-br from-blue-600/10 via-transparent to-indigo-600/15" />
      <div className="relative z-10 grid grid-cols-2 gap-12">
        <div className="flex flex-col justify-center">
          <div className="mt-6 space-y-4">
            <div
              className="text-3xl font-semibold leading-tight text-foreground"
              style={{opacity: signalOpacity}}
            >
              {SIGNAL_LINE}
            </div>
            <div
              className="text-2xl font-semibold leading-tight text-muted-foreground"
              style={{opacity: ruleOpacity}}
            >
              {RULE_LINE}
            </div>
          </div>
        </div>

        <div className="relative space-y-6">
          {CARDS.slice(0, 3).map((card, index) => {
            const start = index * 8;
            const progress = spring({
              frame: frame - start,
              fps,
              config: MOTION.spring,
            });
            const translateY = interpolate(progress, [0, 1], [60, 0]);
            const opacity = interpolate(progress, [0, 1], [0, 1]);

            return (
              <div
                key={card.subject}
                style={{
                  transform: `translateY(${translateY}px)`,
                  opacity,
                  borderRadius: 24,
                }}
              >
                <SignalCard {...card} startFrame={start} />
              </div>
            );
          })}
        </div>
      </div>
    </SceneFrame>
  );
};
