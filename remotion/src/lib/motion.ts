import {Easing, interpolate, spring, type SpringConfig} from 'remotion';

export const clamp = (v: number) => Math.max(0, Math.min(1, v));

export const fadeIn = (frame: number, start: number, duration: number) => {
  return interpolate(frame, [start, start + duration], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
};

export const slideUp = (frame: number, start: number, duration: number, distancePx: number) => {
  const t = interpolate(frame, [start, start + duration], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
  return (1 - t) * distancePx;
};

export const pop = (frame: number, fps: number, start: number, cfg?: Partial<SpringConfig>) => {
  const config: SpringConfig = {damping: 18, stiffness: 220, mass: 0.9, overshootClamping: false, ...cfg};
  const p = spring({frame: frame - start, fps, config});
  return interpolate(p, [0, 1], [0.94, 1]);
};
