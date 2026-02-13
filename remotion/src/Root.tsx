import React from 'react';
import {Composition, Folder} from 'remotion';

import './styles/tailwind.css';
import {FeatureSpotlightReel, FeatureSpotlightReelSchema} from './compositions/FeatureSpotlightReel';
import {LaunchIntroReel, LaunchIntroReelSchema} from './compositions/LaunchIntroReel';
import {TutorDexSignalReel, TUTORDEX_SIGNAL_DURATION, TUTORDEX_SIGNAL_FPS} from './compositions/TutorDexSignalReel/Video';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Folder name="Reels">
        <Composition
          id="TutorDex-Signal-Reel"
          component={TutorDexSignalReel}
          durationInFrames={TUTORDEX_SIGNAL_DURATION}
          fps={TUTORDEX_SIGNAL_FPS}
          width={1080}
          height={1920}
        />
        <Composition
          id="Launch-Intro-Reel"
          component={LaunchIntroReel}
          durationInFrames={15 * 30}
          fps={30}
          width={1080}
          height={1920}
          schema={LaunchIntroReelSchema}
          defaultProps={{
            regionPill: 'For Tutors in Singapore',
            hook: 'Stop scrolling Telegram.',
            headlineA: 'All tuition assignments.',
            headlineB: 'One platform.',
            proofPoints: ['Real-time updates', 'No spam, ever', '100% free for tutors'],
            trustLine: 'Open-likelihood is a best-effort guess — not a promise.',
            cta: 'Join TutorDex',
            ctaSub: 'View live assignments today',
          }}
        />

        <Composition
          id="Feature-Spotlight-Reel"
          component={FeatureSpotlightReel}
          durationInFrames={15 * 30}
          fps={30}
          width={1080}
          height={1920}
          schema={FeatureSpotlightReelSchema}
          defaultProps={{
            hook: 'New feature',
            featureName: 'Open-likelihood tiers',
            benefits: ['Know what is likely still open', 'See posted vs bumped timestamps', 'Apply with less wasted effort'],
            cta: 'Try it on TutorDex',
          }}
        />
      </Folder>
    </>
  );
};
