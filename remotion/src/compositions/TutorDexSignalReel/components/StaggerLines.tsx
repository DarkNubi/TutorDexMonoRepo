import React from 'react';
import {spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {cn} from '@/lib/cn';

type StaggerLinesProps = {
  lines: string[];
  startFrame?: number;
  stagger?: number;
  className?: string;
  lineClassName?: string;
};

export const StaggerLines: React.FC<StaggerLinesProps> = ({
  lines,
  startFrame = 0,
  stagger = 8,
  className,
  lineClassName,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      {lines.map((line, index) => {
        const localFrame = frame - startFrame - index * stagger;
        const progress = spring({frame: localFrame, fps, config: {damping: 18, stiffness: 160}});
        const translateY = 18 * (1 - progress);
        const opacity = progress;

        return (
          <div
            key={line}
            className={cn('tracking-tight', lineClassName)}
            style={{transform: `translateY(${translateY}px)`, opacity}}
          >
            {line}
          </div>
        );
      })}
    </div>
  );
};
