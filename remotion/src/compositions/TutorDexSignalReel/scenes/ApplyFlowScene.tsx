import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {Button} from '@/components/ui/button';
import {Badge} from '@/components/ui/badge';
import {SceneFrame} from '../components/SceneFrame';
import {StaggerLines} from '../components/StaggerLines';

const STATUS = [
  {label: 'Applied', className: 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-200'},
  {label: 'Viewed', className: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-200'},
  {label: 'Shortlisted', className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200'},
];

export const ApplyFlowScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ripple = interpolate(frame, [10, 24], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const harderFade = interpolate(frame, [24, 48], [1, 0.6], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <SceneFrame className="px-16 py-20">
      <div className="absolute inset-0 bg-gradient-to-b from-blue-600/8 via-transparent to-indigo-600/10" />
      <div className="relative z-10 grid grid-cols-2 gap-12 items-center">
        <div>
          <div className="text-4xl font-bold tracking-tight">
            <div>apply smarter.</div>
            <div style={{opacity: harderFade}}>not harder.</div>
          </div>
          <div className="mt-8 text-lg text-muted-foreground">
            Status moves with you, not against you.
          </div>
        </div>

        <div className="flex flex-col items-center gap-6">
          <div className="relative">
            <Button className="rounded-2xl px-10 py-6 text-lg font-bold">
              Apply
            </Button>
            <div
              className="absolute inset-0 rounded-2xl border border-blue-500/40"
              style={{
                transform: `scale(${1 + ripple * 0.25})`,
                opacity: 0.6 * (1 - ripple),
              }}
            />
          </div>

          <div className="flex items-center gap-3">
            {STATUS.map((status, index) => {
              const progress = spring({
                frame: frame - 16 - index * 10,
                fps,
                config: {damping: 18, stiffness: 140},
              });
              return (
                <Badge
                  key={status.label}
                  className={`${status.className} text-xs font-bold uppercase tracking-wide`}
                  style={{
                    opacity: progress,
                    transform: `translateY(${12 * (1 - progress)}px)`,
                  }}
                >
                  {status.label}
                </Badge>
              );
            })}
          </div>
        </div>
      </div>
    </SceneFrame>
  );
};
