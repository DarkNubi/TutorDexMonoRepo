import {Config} from '@remotion/cli/config';
import {enableTailwind} from '@remotion/tailwind';
import {resolve} from 'node:path';

Config.overrideWebpackConfig((currentConfiguration) => {
  const config = enableTailwind(currentConfiguration);

  config.resolve = config.resolve ?? {};
  config.resolve.alias = config.resolve.alias ?? {};
  config.resolve.alias['@'] = resolve(process.cwd(), '../TutorDexWebsite/src');

  return config;
});
