import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
// Reuse TutorDexWebsite UI primitives to keep styling aligned with the site.
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Badge} from '@/components/ui/badge';
import {ProgressBar} from './ProgressBar';

export type SignalCardProps = {
  subject: string;
  level: string;
  location: string;
  rate: string;
  source: string;
  likelyFilled: string;
  freshness: number;
  match: number;
  startFrame: number;
  compact?: boolean;
};

export const SignalCard: React.FC<SignalCardProps> = ({
  subject,
  level,
  location,
  rate,
  source,
  likelyFilled,
  freshness,
  match,
  startFrame,
  compact = false,
}) => {
  const frame = useCurrentFrame();
  const statusOpacity = interpolate(frame, [startFrame + 12, startFrame + 22], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <Card className={compact ? 'rounded-xl' : 'rounded-2xl'}>
      <CardHeader className={compact ? 'p-4 pb-2' : undefined}>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className={compact ? 'text-base' : 'text-lg'}>{subject}</CardTitle>
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mt-1">
              {level} • {location}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Match score</div>
            <Badge className="mt-1 bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300">
              {match}%
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className={compact ? 'p-4 pt-0' : undefined}>
        <div className="flex items-center justify-between text-sm font-semibold">
          <div className="text-muted-foreground uppercase tracking-wide text-xs">Rate</div>
          <div className="text-blue-600 dark:text-blue-300 font-bold">{rate}</div>
        </div>
        <div className="mt-4 space-y-3">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <span>Source</span>
            <span className="text-foreground">{source}</span>
          </div>
          <div
            className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground"
            style={{opacity: statusOpacity}}
          >
            <span>Likely filled</span>
            <span className="text-foreground">{likelyFilled}</span>
          </div>
          <div>
            <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <span>Freshness</span>
              <span>{freshness}%</span>
            </div>
            <ProgressBar value={freshness} start={startFrame + 6} fillClassName="bg-blue-600/35" />
          </div>
          <div>
            <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <span>Match score</span>
              <span>{match}%</span>
            </div>
            <ProgressBar value={match} start={startFrame + 10} fillClassName="bg-foreground/30" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
