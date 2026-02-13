import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {cn} from '@/lib/cn';
import {MOTION} from '../constants';

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
    config: MOTION.spring,
  });
  const width = interpolate(progress, [0, 1], [0, value], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div className={cn('h-2 w-full rounded-full bg-muted/60 overflow-hidden', className)}>
      <div
        className={cn('h-full rounded-full bg-foreground/35', fillClassName)}
        style={{width: `${width}%`}}
      />
    </div>
  );
};
