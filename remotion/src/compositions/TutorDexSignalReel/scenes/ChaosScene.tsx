import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {SceneFrame} from '../components/SceneFrame';

const CHAOS_WORDS = [
  {text: 'URGENT!!!', x: 80, y: 140, rotate: -8, size: 72, color: 'text-red-400'},
  {text: '$60/hr', x: 640, y: 180, rotate: 6, size: 64, color: 'text-emerald-300'},
  {text: 'taken', x: 140, y: 360, rotate: -4, size: 56, color: 'text-orange-300'},
  {text: 'available??', x: 520, y: 310, rotate: 4, size: 50, color: 'text-teal-200'},
  {text: 'already filled', x: 520, y: 420, rotate: 3, size: 52, color: 'text-rose-300'},
  {text: 'bump', x: 180, y: 620, rotate: -6, size: 60, color: 'text-sky-300'},
  {text: 'still open??', x: 520, y: 660, rotate: 5, size: 50, color: 'text-yellow-300'},
  {text: 'duplicate', x: 120, y: 900, rotate: -2, size: 58, color: 'text-violet-300'},
];

const METRICS = ['127 new messages.', '4 duplicates.', '3 ghosted agencies.', '0 clarity.'];

const MESSAGES = [
  {text: 'P5 Math • $60/hr • Bukit Timah', duplicate: true, status: 'already filled'},
  {text: 'Sec 3 Chem • $60/hr • Online', duplicate: false, status: 'still open??'},
  {text: 'JC1 Physics • $55/hr • Bishan', duplicate: true, status: 'duplicate'},
  {text: 'Pri 6 English • $60/hr • Tanjong Pagar', duplicate: false, status: 'bump'},
  {text: 'Sec 2 Math • $60/hr • Serangoon', duplicate: false, status: 'available??'},
  {text: 'JC2 Bio • $65/hr • Online', duplicate: true, status: 'taken'},
];

const NOTIFS = ['New assignment posted', 'Reply from agency', 'Listing updated'];

type ChaosSceneProps = {
  durationInFrames: number;
};

export const ChaosScene: React.FC<ChaosSceneProps> = ({durationInFrames}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const introEnd = 2 * fps;
  const chaosEnd = 5 * fps;
  const fadeOut = interpolate(frame, [durationInFrames - 18, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const jitterX = Math.sin(frame * 0.42) * 4;
  const jitterY = Math.cos(frame * 0.33) * 3;
  const scrollY = interpolate(frame, [introEnd, chaosEnd], [0, -220], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const introOpacity = interpolate(frame, [0, 10, introEnd - 6, introEnd], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const chaosOpacity = interpolate(frame, [introEnd - 6, introEnd + 8], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const metricsOpacity = interpolate(frame, [chaosEnd - 6, chaosEnd + 6], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const introLine1 = "it’s 11:48pm.";
  const introLine2 = 'you’re still scrolling.';
  const introChars1 = Math.floor(interpolate(frame, [0, introEnd - 10], [0, introLine1.length], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  }));
  const introChars2 = Math.floor(interpolate(frame, [14, introEnd - 2], [0, introLine2.length], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  }));

  return (
    <SceneFrame
      className="overflow-hidden"
      style={{
        background: 'linear-gradient(180deg, #04070f 0%, #050b1a 100%)',
      }}
    >
      <div className="absolute inset-0 bg-black/50" />

      <AbsoluteFill
        className="flex items-center justify-center"
        style={{opacity: introOpacity}}
      >
        <div className="text-center text-white">
          <div className="text-4xl font-semibold tracking-tight">
            {introLine1.slice(0, introChars1)}
          </div>
          <div className="mt-4 text-3xl font-semibold tracking-tight text-white/80">
            {introLine2.slice(0, introChars2)}
          </div>
        </div>
      </AbsoluteFill>

      <AbsoluteFill
        className="px-16 py-24"
        style={{
          opacity: chaosOpacity,
          transform: `translate(${jitterX}px, ${jitterY}px)`,
        }}
      >
        <div className="absolute inset-0">
          <div
            className="absolute top-10 left-16 right-16 h-10 rounded-2xl border border-white/10 bg-white/5"
            style={{backdropFilter: 'blur(6px)'}}
          />
          {NOTIFS.map((note, index) => {
            const slide = interpolate(frame, [introEnd + index * 4, introEnd + index * 4 + 8], [20, 0], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            });
            const opacity = interpolate(frame, [introEnd + index * 4, introEnd + index * 4 + 8], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            });
            return (
              <div
                key={note}
                className="absolute left-24 right-24 rounded-2xl border border-white/10 bg-white/10 px-4 py-2 text-sm text-white/80"
                style={{
                  top: 70 + index * 42,
                  transform: `translateY(${slide}px)`,
                  opacity,
                  backdropFilter: 'blur(6px)',
                }}
              >
                {note}
              </div>
            );
          })}
        </div>

        <div className="relative mt-32 space-y-4" style={{transform: `translateY(${scrollY}px)`}}>
          {MESSAGES.map((msg, index) => (
            <div
              key={msg.text}
              className={`rounded-2xl px-5 py-4 text-base font-semibold text-white/90 shadow-lg ${
                msg.duplicate ? 'border border-red-400/70' : 'border border-white/10'
              }`}
              style={{
                background: 'rgba(255,255,255,0.08)',
                backdropFilter: 'blur(6px)',
              }}
            >
              <div className="flex items-center justify-between">
                <div>{msg.text}</div>
                <div className="text-xs uppercase tracking-wide text-white/50">2m ago</div>
              </div>
              <div className="mt-2 text-xs font-bold uppercase tracking-wide text-white/60">
                {msg.status}
              </div>
            </div>
          ))}
        </div>
      </AbsoluteFill>

      {CHAOS_WORDS.map((word, index) => {
        const localJitterX = Math.sin((frame + index * 13) * 0.35) * 8;
        const localJitterY = Math.cos((frame + index * 17) * 0.28) * 6;
        const appear = interpolate(frame, [introEnd + index * 2, introEnd + index * 2 + 8], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        const flicker = 0.35 + 0.65 * Math.abs(Math.sin((frame + index * 9) * 0.4));

        return (
          <div
            key={word.text}
            className={`absolute font-black uppercase tracking-tight ${word.color}`}
            style={{
              left: word.x + localJitterX,
              top: word.y + localJitterY,
              fontSize: word.size,
              transform: `rotate(${word.rotate}deg)`,
              opacity: appear * flicker * fadeOut * chaosOpacity,
              textShadow: '0 8px 30px rgba(0,0,0,0.55)',
            }}
          >
            {word.text}
          </div>
        );
      })}

      <AbsoluteFill className="flex items-center justify-center">
        <div className="space-y-3 text-center">
          {METRICS.map((line, index) => {
            const start = chaosEnd - 10 + index * 6;
            const opacity = interpolate(frame, [start, start + 10], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            });

            return (
              <div
                key={line}
                className="text-4xl font-bold tracking-tight text-white"
                style={{opacity: opacity * metricsOpacity}}
              >
                {line}
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </SceneFrame>
  );
};
