# TutorDex Remotion (Reels)

Vertical 9:16 templates for TutorDex marketing reels.

## Setup

```bash
cd remotion
npm install
```

## Studio

```bash
npm run dev
```

## Preview (Remotion)

```bash
npx remotion preview
```

## Render

```bash
mkdir -p out
npm run render:launch
npm run render:feature
npx remotion render TutorDex-Signal-Reel out/tutordex-signal-reel.mp4
```

## Generate a “what changed?” brief
```bash
cd remotion
npm run brief -- --from <old-ref> --to <new-ref> --paths TutorDexWebsite,TutorDexBackend
```
