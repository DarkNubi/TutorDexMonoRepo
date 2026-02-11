import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {cn} from '@/lib/cn';

type ProgressBarProps = {
  value: number;
  start: number;
  className?: string;
  fillClassName?: string;
};

export const ProgressBar: React.FC<ProgressBarProps> = ({value, start, className, fillClassName}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = spring({
    frame: frame - start,
    fps,
    config: {damping: 18, stiffness: 120},
  });
  const width = interpolate(progress, [0, 1], [0, value], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div className={cn('h-2 w-full rounded-full bg-muted/70 overflow-hidden', className)}>
      <div
        className={cn('h-full rounded-full bg-gradient-to-r from-blue-600 to-indigo-600', fillClassName)}
        style={{width: `${width}%`}}
      />
    </div>
  );
};
