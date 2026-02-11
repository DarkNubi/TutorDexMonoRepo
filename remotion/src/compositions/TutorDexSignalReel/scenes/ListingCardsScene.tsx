import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {SceneFrame} from '../components/SceneFrame';
import {SignalCard} from '../components/SignalCard';
import {StaggerLines} from '../components/StaggerLines';

const RULE_LINES = ['no pay-to-win.', 'no hidden boosts.', 'no fake urgency.'];

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
  const tooltipOpacity = interpolate(frame, [12, 30], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <SceneFrame className="px-16 py-20">
      <div className="absolute inset-0 bg-gradient-to-br from-blue-600/10 via-transparent to-indigo-600/15" />
      <div className="relative z-10 grid grid-cols-2 gap-12">
        <div className="flex flex-col justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Signal stack</div>
            <div className="text-4xl font-bold tracking-tight mt-3">real listings.</div>
            <div className="text-4xl font-bold tracking-tight">ranked by likelihood.</div>
          </div>
          <StaggerLines
            lines={RULE_LINES}
            startFrame={12}
            stagger={10}
            className="text-2xl font-semibold text-muted-foreground"
          />
        </div>

        <div className="relative space-y-6">
          {CARDS.map((card, index) => {
            const start = index * 8;
            const progress = spring({
              frame: frame - start,
              fps,
              config: {damping: 16, stiffness: 120},
            });
            const translateY = interpolate(progress, [0, 1], [60, 0]);
            const opacity = interpolate(progress, [0, 1], [0, 1]);
            const glow = 0.22 + 0.08 * Math.sin((frame + index * 20) * 0.08);

            return (
              <div
                key={card.subject}
                style={{
                  transform: `translateY(${translateY}px)`,
                  opacity,
                  boxShadow: `0 20px 45px rgba(37,99,235,${glow})`,
                  borderRadius: 24,
                }}
              >
                <SignalCard {...card} startFrame={start} />
              </div>
            );
          })}

          <div
            className="absolute -right-2 top-16 w-64 rounded-2xl border border-border bg-background/90 p-4 text-sm text-foreground shadow-xl"
            style={{opacity: tooltipOpacity}}
          >
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Intelligence
            </div>
            <div className="mt-2 text-sm font-semibold">Agency avg response time: 2h</div>
            <div className="mt-1 text-sm font-semibold">Fill speed: 18h median</div>
          </div>
        </div>
      </div>
    </SceneFrame>
  );
};
