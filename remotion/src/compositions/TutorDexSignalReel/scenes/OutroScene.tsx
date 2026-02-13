import React from 'react';
import {Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {SceneFrame} from '../components/SceneFrame';
import {StaggerLines} from '../components/StaggerLines';

const LOCKUP = ['TutorDex.', 'The operating system for tutor decisions.'];
const FOOTER = ['Not an agency. Not a marketplace. Just clarity.'];

export const OutroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const fadeIn = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: 'clamp',
  });
  const fadeOut = interpolate(frame, [200, 240], [1, 0], {
    extrapolateRight: 'clamp',
  });
  const fade = fadeIn * fadeOut;

  return (
    <SceneFrame className="items-center justify-center">
      <div
        className="absolute inset-0"
        style={{
          background: 'linear-gradient(180deg, rgba(5,11,26,0.9) 0%, rgba(5,11,26,1) 100%)',
          opacity: fade,
        }}
      />

      <div className="relative z-10 flex flex-col items-center gap-10" style={{opacity: fade}}>
        <div className="flex items-center gap-4">
          <Img
            src={staticFile('TutorDex-icon-512.png')}
            style={{width: 72, height: 72, borderRadius: 18}}
          />
          <div className="text-3xl font-bold tracking-tight">TutorDex</div>
        </div>

        <StaggerLines
          lines={LOCKUP}
          startFrame={6}
          stagger={14}
          className="text-4xl font-bold text-center"
          lineClassName="leading-tight"
        />

        <StaggerLines
          lines={FOOTER}
          startFrame={40}
          stagger={12}
          className="text-lg font-semibold text-muted-foreground text-center"
        />
      </div>
    </SceneFrame>
  );
};
