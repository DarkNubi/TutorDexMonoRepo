import React from 'react';
import {AbsoluteFill} from 'remotion';
import {cn} from '@/lib/cn';

type SceneFrameProps = {
  className?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
};

export const SceneFrame: React.FC<SceneFrameProps> = ({className, style, children}) => {
  return (
    <AbsoluteFill className={cn('dark relative bg-background text-foreground', className)} style={style}>
      {children}
    </AbsoluteFill>
  );
};
