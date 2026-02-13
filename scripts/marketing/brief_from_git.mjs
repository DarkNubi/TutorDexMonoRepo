import {execSync} from 'node:child_process';

function readArg(name) {
  const idx = process.argv.indexOf(name);
  if (idx === -1) return null;
  const next = process.argv[idx + 1];
  if (!next || next.startsWith('--')) return '';
  return next;
}

function splitCsv(v) {
  return String(v || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

function sh(cmd) {
  return execSync(cmd, {encoding: 'utf8'}).trim();
}

const from = readArg('--from');
const to = readArg('--to') || 'HEAD';
const paths = splitCsv(readArg('--paths'));
const maxCommits = Number.parseInt(readArg('--max-commits') || '30', 10);
const range = from ? `${from}..${to}` : null;
const pathArgs = paths.length ? ` -- ${paths.map((p) => JSON.stringify(p)).join(' ')}` : '';

const changedRaw = sh(`git diff --name-status ${range ? range : to}${pathArgs}`);
const changedFiles = changedRaw
  ? changedRaw
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [status, ...rest] = line.split('\t');
        return {status, path: rest.join('\t')};
      })
  : [];

const commitsRaw = sh(`git log ${range ? range : to} --no-merges -n ${maxCommits} --pretty=format:%s${pathArgs}`);
const commitSubjects = commitsRaw ? commitsRaw.split('\n').map((s) => s.trim()).filter(Boolean) : [];

const pathsSet = new Set(changedFiles.map((f) => f.path));
const hasAssignmentsUI = [...pathsSet].some(
  (p) => p.includes('TutorDexWebsite/src/page-assignments') || p.includes('TutorDexWebsite/assignments.html')
);
const hasLandingUI = [...pathsSet].some((p) => p.includes('TutorDexWebsite/src/landing'));
const hasBackend = [...pathsSet].some((p) => p.includes('TutorDexBackend/'));
const hasAggregator = [...pathsSet].some((p) => p.includes('TutorDexAggregator/'));

const suggestedAngles = [];
if (hasAssignmentsUI) {
  suggestedAngles.push(
    'Assignments feed update: show the problem (stale posts) → show TutorDex signal (open-likelihood, timestamps, clean cards) → CTA.'
  );
}
if (hasLandingUI) {
  suggestedAngles.push('Landing update: refresh hook + benefits, keep pace fast, strong CTA to “View Live Assignments”.');
}
if (hasBackend || hasAggregator) {
  suggestedAngles.push(
    'Reliability/trust update: highlight “real listings”, “visible sources”, “best-effort scores”, and “no fabricated listings”.'
  );
}
if (!suggestedAngles.length) {
  suggestedAngles.push('Feature spotlight: pick 1 visible UX improvement and show it in 3 beats (hook → demo → CTA).');
}

const out = {
  generatedAt: new Date().toISOString(),
  range: range || to,
  filters: {paths, maxCommits},
  changedFiles,
  commitSubjects,
  suggestedFeatureVideoAngles: suggestedAngles,
};

process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);

