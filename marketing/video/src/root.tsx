import {Composition} from 'remotion';
import {SkillLaunch} from './skill-launch';

export const VideoRoot: React.FC = () => {
  return (
    <Composition
      id="SkillLaunch"
      component={SkillLaunch}
      durationInFrames={1620}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
