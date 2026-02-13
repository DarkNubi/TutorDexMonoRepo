import React from 'react';

const MESSAGES = [
  {text: 'P5 Math • $60/hr • Bukit Timah', duplicate: true, status: 'already filled'},
  {text: 'Sec 3 Chem • $60/hr • Online', duplicate: false, status: 'still open??'},
  {text: 'JC1 Physics • $55/hr • Bishan', duplicate: true, status: 'duplicate'},
  {text: 'Pri 6 English • $60/hr • Tanjong Pagar', duplicate: false, status: 'bump'},
  {text: 'Sec 2 Math • $60/hr • Serangoon', duplicate: false, status: 'available??'},
  {text: 'JC2 Bio • $65/hr • Online', duplicate: true, status: 'taken'},
];

const NOTIFS = ['New assignment posted', 'Reply from agency', 'Listing updated'];

type TelegramFeedProps = {
  scrollY: number;
  blur?: number;
  opacity?: number;
};

export const TelegramFeed: React.FC<TelegramFeedProps> = ({scrollY, blur = 3, opacity = 1}) => {
  return (
    <div
      className="absolute inset-0 px-16 py-24"
      style={{
        opacity,
        filter: `blur(${blur}px)`,
      }}
    >
      <div className="absolute inset-0">
        <div
          className="absolute top-10 left-16 right-16 h-10 rounded-2xl border border-white/10 bg-white/5"
          style={{backdropFilter: 'blur(6px)'}}
        />
        {NOTIFS.map((note, index) => (
          <div
            key={note}
            className="absolute left-24 right-24 rounded-2xl border border-white/10 bg-white/10 px-4 py-2 text-sm text-white/80"
            style={{
              top: 70 + index * 42,
              backdropFilter: 'blur(6px)',
            }}
          >
            {note}
          </div>
        ))}
      </div>

      <div className="relative mt-32 space-y-4" style={{transform: `translateY(${scrollY}px)`}}>
        {MESSAGES.map((msg) => (
          <div
            key={msg.text}
            className={`rounded-2xl px-5 py-4 text-base font-semibold text-white/90 shadow-lg ${
              msg.duplicate ? 'border border-red-400/60' : 'border border-white/10'
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
    </div>
  );
};
