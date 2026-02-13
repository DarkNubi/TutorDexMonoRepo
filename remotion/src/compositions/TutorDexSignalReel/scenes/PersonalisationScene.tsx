import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {SceneFrame} from '../components/SceneFrame';
import {SignalCard} from '../components/SignalCard';

const CARDS = [
  {
    subject: 'Math',
    level: 'Secondary 2',
    location: 'Online',
    rate: '$60/hr',
    source: 'Agency X',
    likelyFilled: 'Low',
    freshness: 88,
    match: 80,
    ghost: false,
  },
  {
    subject: 'Physics',
    level: 'JC2',
    location: 'Serangoon',
    rate: '$60/hr',
    source: 'Agency X',
    likelyFilled: 'High',
    freshness: 62,
    match: 44,
    ghost: true,
  },
  {
    subject: 'Biology',
    level: 'JC1',
    location: 'Online',
    rate: '$60/hr',
    source: 'Agency X',
    likelyFilled: 'Low',
    freshness: 86,
    match: 83,
    ghost: false,
  },
];

export const PersonalisationScene: React.FC = () => {
  const frame = useCurrentFrame();
  const removeProgress = interpolate(frame, [12, 48], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <SceneFrame className="px-16 py-16">
      <div className="absolute inset-0 bg-gradient-to-tr from-blue-600/8 via-transparent to-indigo-600/12" />
      <div className="relative z-10 grid grid-cols-2 gap-12">
        <div />
        <div className="space-y-4">
          {CARDS.map((card, index) => {
            const isGhost = card.ghost;
            const ghostOpacity = isGhost ? 1 - removeProgress : 1;
            const ghostScale = isGhost ? 1 - 0.08 * removeProgress : 1;
            const shiftUp = index > 1 ? -80 * removeProgress : 0;

            return (
              <div
                key={card.subject}
                style={{
                  opacity: ghostOpacity,
                  transform: `translateY(${shiftUp}px) scale(${ghostScale})`,
                }}
              >
                <SignalCard {...card} startFrame={6 + index * 6} compact />
              </div>
            );
          })}
        </div>
      </div>
    </SceneFrame>
  );
};
