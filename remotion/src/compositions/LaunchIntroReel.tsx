import React, {useMemo} from 'react';
import {AbsoluteFill, Img, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {z} from 'zod';

import {brand} from '../lib/brand';
import {fadeIn, pop, slideUp} from '../lib/motion';

export const LaunchIntroReelSchema = z.object({
  regionPill: z.string(),
  hook: z.string(),
  headlineA: z.string(),
  headlineB: z.string(),
  proofPoints: z.array(z.string()).min(1).max(4),
  trustLine: z.string(),
  cta: z.string(),
  ctaSub: z.string(),
});

export type LaunchIntroReelProps = z.infer<typeof LaunchIntroReelSchema>;

const SafeArea: React.FC<React.PropsWithChildren> = ({children}) => {
  return (
    <div
      style={{
        position: 'absolute',
        left: 72,
        right: 72,
        top: 170,
        bottom: 230,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
      }}
    >
      {children}
    </div>
  );
};

const Pill: React.FC<{label: string}> = ({label}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = pop(frame, fps, 0);
  const o = fadeIn(frame, 0, Math.round(0.6 * fps));
  return (
    <div
      style={{
        transform: `scale(${s})`,
        opacity: o,
        alignSelf: 'flex-start',
        padding: '14px 18px',
        borderRadius: 999,
        background: 'rgba(37, 99, 235, 0.18)',
        border: `1px solid ${brand.colors.faint}`,
        color: 'rgba(220, 234, 255, 0.95)',
        fontSize: 30,
        fontWeight: 700,
        letterSpacing: -0.2,
      }}
    >
      {label}
    </div>
  );
};

const BigLine: React.FC<{text: string; start: number; duration: number; tone?: 'white' | 'gradient'}> = ({
  text,
  start,
  duration,
  tone = 'white',
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const y = slideUp(frame, start, duration, 60);
  const o = fadeIn(frame, start, duration);
  const s = pop(frame, fps, start, {damping: 22, stiffness: 240});
  const gradient =
    'linear-gradient(90deg, rgba(37,99,235,1) 0%, rgba(79,70,229,1) 55%, rgba(20,184,166,1) 100%)';

  return (
    <div
      style={{
        opacity: o,
        transform: `translateY(${y}px) scale(${s})`,
        fontSize: 96,
        lineHeight: 1.04,
        fontWeight: 900,
        letterSpacing: -1.6,
        color: tone === 'white' ? brand.colors.white : undefined,
        background: tone === 'gradient' ? gradient : undefined,
        WebkitBackgroundClip: tone === 'gradient' ? 'text' : undefined,
        backgroundClip: tone === 'gradient' ? 'text' : undefined,
        WebkitTextFillColor: tone === 'gradient' ? 'transparent' : undefined,
      }}
    >
      {text}
    </div>
  );
};

const AssignmentCard: React.FC<{subject: string; level: string; rate: string; idx: number}> = ({subject, level, rate, idx}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const start = Math.round((0.2 + idx * 0.16) * fps);
  const o = fadeIn(frame, start, Math.round(0.5 * fps));
  const y = slideUp(frame, start, Math.round(0.7 * fps), 34);
  return (
    <div
      style={{
        opacity: o,
        transform: `translateY(${y}px)`,
        borderRadius: 28,
        padding: 26,
        background: 'rgba(255,255,255,0.06)',
        border: `1px solid ${brand.colors.faint}`,
        boxShadow: '0 30px 80px rgba(0,0,0,0.35)',
      }}
    >
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16}}>
        <div style={{minWidth: 0}}>
          <div style={{fontSize: 34, fontWeight: 800, letterSpacing: -0.4, color: brand.colors.white}}>{subject}</div>
          <div style={{fontSize: 26, fontWeight: 700, color: brand.colors.muted, marginTop: 6}}>{level}</div>
        </div>
        <div
          style={{
            padding: '10px 14px',
            borderRadius: 999,
            background: 'rgba(16,185,129,0.16)',
            border: '1px solid rgba(16,185,129,0.35)',
            color: 'rgba(167, 243, 208, 0.95)',
            fontSize: 22,
            fontWeight: 800,
            whiteSpace: 'nowrap',
          }}
        >
          New
        </div>
      </div>
      <div style={{display: 'flex', justifyContent: 'space-between', marginTop: 18, gap: 14}}>
        <div style={{fontSize: 24, fontWeight: 700, color: 'rgba(255,255,255,0.8)'}}>via Agency</div>
        <div style={{fontSize: 28, fontWeight: 900, color: 'rgba(96,165,250,0.98)'}}>{rate}</div>
      </div>
    </div>
  );
};

const ProofRow: React.FC<{items: string[]; start: number}> = ({items, start}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const o = fadeIn(frame, start, Math.round(0.7 * fps));
  const y = slideUp(frame, start, Math.round(0.7 * fps), 30);
  return (
    <div style={{opacity: o, transform: `translateY(${y}px)`, display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 22}}>
      {items.map((label) => (
        <div
          key={label}
          style={{
            padding: '12px 14px',
            borderRadius: 999,
            background: 'rgba(255,255,255,0.06)',
            border: `1px solid ${brand.colors.faint}`,
            fontSize: 24,
            fontWeight: 800,
            color: 'rgba(255,255,255,0.88)',
          }}
        >
          {label}
        </div>
      ))}
    </div>
  );
};

export const LaunchIntroReel: React.FC<LaunchIntroReelProps> = ({
  regionPill,
  hook,
  headlineA,
  headlineB,
  proofPoints,
  trustLine,
  cta,
  ctaSub,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  const bg = useMemo(() => {
    const t = durationInFrames ? frame / durationInFrames : 0;
    const a = 0.55 + 0.08 * Math.sin(t * Math.PI * 2);
    return `radial-gradient(1000px 900px at 20% 10%, rgba(37,99,235,${a}) 0%, rgba(79,70,229,0.22) 45%, rgba(20,184,166,0.12) 75%, rgba(5,11,26,1) 100%)`;
  }, [durationInFrames, frame]);

  return (
    <AbsoluteFill
      style={{
        background: bg,
        fontFamily: brand.typography.fontFamily,
      }}
    >
      <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(0,0,0,0.25) 0%, rgba(0,0,0,0.45) 65%, rgba(0,0,0,0.62) 100%)'}} />

      <SafeArea>
        <Sequence from={0} durationInFrames={Math.round(2.3 * fps)}>
          <div style={{display: 'flex', alignItems: 'center', gap: 16, marginBottom: 34}}>
            <Img
              src={staticFile('TutorDex-icon-128.png')}
              style={{width: 86, height: 86, borderRadius: 22, objectFit: 'contain', background: 'rgba(255,255,255,0.06)'}}
            />
            <div style={{display: 'flex', flexDirection: 'column', gap: 6}}>
              <div style={{fontSize: 44, fontWeight: 900, letterSpacing: -0.8, color: brand.colors.white}}>TutorDex</div>
              <div style={{fontSize: 26, fontWeight: 750, color: 'rgba(255,255,255,0.78)'}}>Tuition assignments, simplified</div>
            </div>
          </div>
          <Pill label={regionPill} />
        </Sequence>

        <Sequence from={Math.round(2.0 * fps)} durationInFrames={Math.round(4.0 * fps)}>
          <BigLine text={hook} start={Math.round(2.0 * fps)} duration={Math.round(0.9 * fps)} tone="white" />
          <div style={{marginTop: 18, fontSize: 34, fontWeight: 750, color: 'rgba(255,255,255,0.78)'}}>
            Stop wasting time on duplicates, bumps, and stale posts.
          </div>
        </Sequence>

        <Sequence from={Math.round(6.0 * fps)} durationInFrames={Math.round(4.6 * fps)}>
          <BigLine text={headlineA} start={Math.round(6.0 * fps)} duration={Math.round(0.8 * fps)} tone="white" />
          <BigLine text={headlineB} start={Math.round(6.35 * fps)} duration={Math.round(0.9 * fps)} tone="gradient" />
          <div style={{display: 'flex', flexDirection: 'column', gap: 16, marginTop: 26}}>
            <AssignmentCard subject="Primary Math" level="P4 • North-East" rate="$55/hr" idx={0} />
            <AssignmentCard subject="Secondary English" level="Sec 2 • Central" rate="$60/hr" idx={1} />
          </div>
        </Sequence>

        <Sequence from={Math.round(10.6 * fps)} durationInFrames={Math.round(2.8 * fps)}>
          <div style={{fontSize: 40, fontWeight: 900, letterSpacing: -0.6, color: brand.colors.white}}>
            Trust-first.
          </div>
          <div style={{marginTop: 10, fontSize: 30, fontWeight: 750, color: 'rgba(255,255,255,0.8)'}}>{trustLine}</div>
          <ProofRow items={proofPoints} start={Math.round(10.8 * fps)} />
        </Sequence>

        <Sequence from={Math.round(13.4 * fps)} durationInFrames={Math.round(1.6 * fps)}>
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
              alignItems: 'flex-start',
              marginTop: 18,
            }}
          >
            <div
              style={{
                fontSize: 64,
                fontWeight: 950,
                letterSpacing: -1.2,
                color: brand.colors.white,
                opacity: fadeIn(frame, Math.round(13.4 * fps), Math.round(0.6 * fps)),
              }}
            >
              {cta}
            </div>
            <div style={{fontSize: 30, fontWeight: 750, color: 'rgba(255,255,255,0.82)'}}>{ctaSub}</div>
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
          <div style={{width: 10, height: 10, borderRadius: 999, background: brand.colors.teal}} />
          <div>tutordex</div>
        </div>
        <div style={{letterSpacing: 0.4}}>Made for tutors in Singapore</div>
      </div>
    </AbsoluteFill>
  );
};

