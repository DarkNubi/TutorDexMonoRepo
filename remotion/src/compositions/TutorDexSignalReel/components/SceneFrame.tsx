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
      <AbsoluteFill
        style={{
          backdropFilter: 'blur(0.6px)',
          opacity: 0.12,
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='80' height='80' filter='url(%23n)' opacity='0.25'/%3E%3C/svg%3E\")",
          opacity: 0.03,
          mixBlendMode: 'soft-light',
        }}
      />
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(120% 120% at 50% 40%, rgba(0,0,0,0) 40%, rgba(0,0,0,0.35) 100%)',
          opacity: 0.35,
        }}
      />
    </AbsoluteFill>
  );
};
