import React from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {z} from 'zod';

import {brand} from '../lib/brand';
import {fadeIn, pop, slideUp} from '../lib/motion';

export const FeatureSpotlightReelSchema = z.object({
  hook: z.string(),
  featureName: z.string(),
  benefits: z.array(z.string()).min(1).max(4),
  cta: z.string(),
});

export type FeatureSpotlightReelProps = z.infer<typeof FeatureSpotlightReelSchema>;

const SafeArea: React.FC<React.PropsWithChildren> = ({children}) => (
  <div
    style={{
      position: 'absolute',
      left: 72,
      right: 72,
      top: 190,
      bottom: 240,
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
    }}
  >
    {children}
  </div>
);

const BenefitRow: React.FC<{text: string; idx: number; start: number}> = ({text, idx, start}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const from = start + Math.round(idx * 0.33 * fps);
  const o = fadeIn(frame, from, Math.round(0.55 * fps));
  const y = slideUp(frame, from, Math.round(0.55 * fps), 26);
  return (
    <div style={{opacity: o, transform: `translateY(${y}px)`, display: 'flex', alignItems: 'flex-start', gap: 14}}>
      <div style={{marginTop: 12, width: 12, height: 12, borderRadius: 999, background: brand.colors.teal}} />
      <div style={{fontSize: 34, fontWeight: 850, lineHeight: 1.18, color: 'rgba(255,255,255,0.88)'}}>{text}</div>
    </div>
  );
};

export const FeatureSpotlightReel: React.FC<FeatureSpotlightReelProps> = ({hook, featureName, benefits, cta}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const t = durationInFrames ? frame / durationInFrames : 0;
  const bg = `radial-gradient(900px 700px at 20% 12%, rgba(79,70,229,${0.52 + 0.08 * Math.sin(t * Math.PI * 2)}) 0%, rgba(20,184,166,0.12) 55%, rgba(5,11,26,1) 100%)`;

  return (
    <AbsoluteFill style={{background: bg, fontFamily: brand.typography.fontFamily}}>
      <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(0,0,0,0.28) 0%, rgba(0,0,0,0.55) 70%, rgba(0,0,0,0.72) 100%)'}} />

      <SafeArea>
        <Sequence from={0} durationInFrames={Math.round(3.2 * fps)}>
          <div
            style={{
              opacity: fadeIn(frame, 0, Math.round(0.8 * fps)),
              transform: `translateY(${slideUp(frame, 0, Math.round(0.8 * fps), 36)}px) scale(${pop(frame, fps, 0)})`,
              fontSize: 38,
              fontWeight: 900,
              letterSpacing: -0.4,
              color: 'rgba(255,255,255,0.86)',
              padding: '14px 18px',
              borderRadius: 999,
              background: 'rgba(255,255,255,0.06)',
              border: `1px solid ${brand.colors.faint}`,
              alignSelf: 'flex-start',
            }}
          >
            {hook}
          </div>
        </Sequence>

        <Sequence from={Math.round(2.2 * fps)} durationInFrames={Math.round(8.0 * fps)}>
          <div
            style={{
              opacity: fadeIn(frame, Math.round(2.2 * fps), Math.round(0.7 * fps)),
              transform: `translateY(${slideUp(frame, Math.round(2.2 * fps), Math.round(0.7 * fps), 48)}px)`,
              fontSize: 92,
              fontWeight: 950,
              letterSpacing: -1.8,
              lineHeight: 1.02,
              color: brand.colors.white,
              marginTop: 18,
            }}
          >
            {featureName}
          </div>

          <div style={{display: 'flex', flexDirection: 'column', gap: 18, marginTop: 34}}>
            {benefits.map((b, i) => (
              <BenefitRow key={`${i}-${b}`} text={b} idx={i} start={Math.round(3.2 * fps)} />
            ))}
          </div>
        </Sequence>

        <Sequence from={Math.round(12.0 * fps)} durationInFrames={Math.round(3.0 * fps)}>
          <div
            style={{
              opacity: fadeIn(frame, Math.round(12.0 * fps), Math.round(0.8 * fps)),
              transform: `translateY(${slideUp(frame, Math.round(12.0 * fps), Math.round(0.8 * fps), 26)}px)`,
              fontSize: 64,
              fontWeight: 950,
              letterSpacing: -1.2,
              color: brand.colors.white,
            }}
          >
            {cta}
          </div>
          <div style={{marginTop: 10, fontSize: 30, fontWeight: 800, color: 'rgba(255,255,255,0.76)'}}>
            Tutor-first. Audit-friendly. No pay-to-win.
          </div>
        </Sequence>
      </SafeArea>

      <div
        style={{
          position: 'absolute',
          left: 72,
          right: 72,
          bottom: 86,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          color: 'rgba(255,255,255,0.70)',
          fontSize: 24,
          fontWeight: 800,
        }}
      >
        <div style={{display: 'flex', alignItems: 'center', gap: 12}}>
          <div style={{width: 10, height: 10, borderRadius: 999, background: brand.colors.blue}} />
          <div>TutorDex</div>
        </div>
        <div style={{letterSpacing: 0.4}}>Live assignments • Real-time</div>
      </div>
    </AbsoluteFill>
  );
};

