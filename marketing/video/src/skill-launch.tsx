import type {CSSProperties, ReactNode} from 'react';
import {
  AbsoluteFill,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

const COLORS = {
  ink: '#17212a',
  muted: '#64717c',
  paper: '#f6f8f9',
  white: '#ffffff',
  night: '#0b1216',
  nightRaised: '#121d23',
  blue: '#326f93',
  blueStrong: '#245a78',
  blueSoft: '#dcecf5',
  line: '#d8dee2',
  warm: '#f0b86e',
  green: '#5e8c75',
};

const FONT = 'Avenir Next, Avenir, Helvetica Neue, Arial, sans-serif';

const clamp = {
  extrapolateLeft: 'clamp' as const,
  extrapolateRight: 'clamp' as const,
};

const fadeFor = (frame: number, duration: number) =>
  interpolate(frame, [0, 16, duration - 18, duration], [0, 1, 1, 0], clamp);

const Scene: React.FC<{duration: number; children: ReactNode; background?: string}> = ({
  duration,
  children,
  background = COLORS.night,
}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        background,
        color: COLORS.white,
        fontFamily: FONT,
        opacity: fadeFor(frame, duration),
        overflow: 'hidden',
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

const GridGlow: React.FC = () => (
  <AbsoluteFill
    style={{
      backgroundImage: [
        'radial-gradient(circle at 78% 18%, rgba(50,111,147,0.24), transparent 34%)',
        'radial-gradient(circle at 18% 82%, rgba(240,184,110,0.1), transparent 30%)',
        'linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px)',
        'linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)',
      ].join(','),
      backgroundSize: 'auto, auto, 72px 72px, 72px 72px',
    }}
  />
);

const Kicker: React.FC<{children: ReactNode; dark?: boolean}> = ({children, dark = false}) => (
  <div
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 10,
      color: dark ? COLORS.blueStrong : '#9ac9e2',
      fontSize: 19,
      fontWeight: 800,
      letterSpacing: '0.13em',
      textTransform: 'uppercase',
    }}
  >
    <span style={{width: 28, height: 3, borderRadius: 4, background: 'currentColor'}} />
    {children}
  </div>
);

const Cursor: React.FC<{x: number; y: number; click?: number}> = ({x, y, click = 0}) => (
  <div
    style={{
      position: 'absolute',
      left: x,
      top: y,
      zIndex: 20,
      transform: `scale(${1 - click * 0.14})`,
      filter: 'drop-shadow(0 5px 8px rgba(0,0,0,0.28))',
    }}
  >
    <svg width="42" height="52" viewBox="0 0 42 52">
      <path d="M5 3L36 31L22 33L16 47L5 3Z" fill="white" stroke="#17212a" strokeWidth="3" />
    </svg>
    {click > 0 ? (
      <span
        style={{
          position: 'absolute',
          left: -18,
          top: -18,
          width: 68,
          height: 68,
          border: `4px solid rgba(50,111,147,${0.75 - click * 0.5})`,
          borderRadius: '50%',
          transform: `scale(${0.35 + click * 1.1})`,
        }}
      />
    ) : null}
  </div>
);

const PainScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const cards = [
    ['Quick Chat', '15 min'],
    ['Coffee Chat', '20 min'],
    ['Advisor Call', '25 min'],
    ['Team Intro', '30 min'],
    ['Working Session', '45 min'],
    ['Partner Session', '50 min'],
    ['Deep Dive', '60 min'],
    ['Workshop', '90 min'],
  ];
  const secondBeat = interpolate(frame, [118, 145], [0, 1], clamp);
  const cursorProgress = interpolate(frame, [55, 175], [0, 1], clamp);
  const cursorX = interpolate(cursorProgress, [0, 0.35, 0.7, 1], [1220, 1510, 1280, 1570]);
  const cursorY = interpolate(cursorProgress, [0, 0.35, 0.7, 1], [285, 410, 590, 730]);
  const click = interpolate(frame % 42, [25, 30, 36], [0, 1, 0], clamp);

  return (
    <Scene duration={240}>
      <GridGlow />
      <div style={{position: 'absolute', left: 112, top: 100, width: 790}}>
        <Kicker>The old way</Kicker>
        <div style={{fontSize: 86, lineHeight: 0.98, fontWeight: 750, letterSpacing: '-0.055em', marginTop: 34}}>
          Scheduling became a scavenger hunt.
        </div>
        <div style={{fontSize: 31, lineHeight: 1.35, color: '#aebbc2', marginTop: 38, maxWidth: 680}}>
          Eight booking links. Different lengths. The same fifteen-minute starts repeated everywhere.
        </div>
        <div
          style={{
            marginTop: 48,
            display: 'inline-flex',
            padding: '14px 20px',
            border: '1px solid rgba(255,255,255,0.16)',
            borderRadius: 12,
            color: secondBeat ? COLORS.warm : '#aebbc2',
            fontSize: 22,
            fontWeight: 650,
            opacity: interpolate(frame, [95, 120], [0.45, 1], clamp),
          }}
        >
          Then cross-reference another calendar.
        </div>
      </div>

      <div style={{position: 'absolute', right: 90, top: 92, width: 790, height: 900}}>
        {cards.map(([name, duration], index) => {
          const row = Math.floor(index / 2);
          const col = index % 2;
          const enter = spring({fps, frame: frame - index * 7, config: {damping: 16, stiffness: 120}});
          const tilt = (index % 3 - 1) * 1.6;
          return (
            <div
              key={name}
              style={{
                position: 'absolute',
                left: col * 360 + (row % 2) * 24,
                top: row * 190,
                width: 326,
                height: 148,
                padding: 24,
                borderRadius: 18,
                border: '1px solid rgba(255,255,255,0.13)',
                background: 'linear-gradient(145deg, #17252c, #111a1f)',
                boxShadow: '0 24px 70px rgba(0,0,0,0.28)',
                transform: `translateY(${(1 - enter) * 120}px) rotate(${tilt * enter}deg) scale(${0.92 + enter * 0.08})`,
                opacity: enter,
              }}
            >
              <div style={{fontSize: 15, color: '#88b9d2', fontWeight: 800, letterSpacing: '0.12em'}}>CALENDLY</div>
              <div style={{fontSize: 29, fontWeight: 750, marginTop: 18}}>{name}</div>
              <div style={{fontSize: 20, color: '#a8b4ba', marginTop: 8}}>{duration}</div>
            </div>
          );
        })}
      </div>
      <Cursor x={cursorX} y={cursorY} click={click} />
    </Scene>
  );
};

const PromptScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const prompt = 'Open Stuart\'s Calendly for the next 45 days and overlay my calendar.';
  const typed = prompt.slice(0, Math.floor(interpolate(frame, [45, 135], [0, prompt.length], clamp)));
  const panelIn = spring({fps, frame: frame - 14, config: {damping: 18, stiffness: 110}});
  const sent = interpolate(frame, [140, 151], [0, 1], clamp);
  return (
    <Scene duration={210} background={COLORS.paper}>
      <div style={{position: 'absolute', left: 110, top: 100, color: COLORS.ink, width: 1680}}>
        <Kicker dark>The turning point</Kicker>
        <div style={{fontSize: 78, fontWeight: 760, letterSpacing: '-0.05em', marginTop: 25}}>
          One prompt replaces the hunt.
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          left: 220,
          right: 220,
          top: 350,
          minHeight: 390,
          borderRadius: 26,
          border: `1px solid ${COLORS.line}`,
          background: COLORS.white,
          boxShadow: '0 34px 100px rgba(31,52,67,0.14)',
          padding: 42,
          color: COLORS.ink,
          transform: `translateY(${(1 - panelIn) * 70}px) scale(${0.97 + panelIn * 0.03})`,
          opacity: panelIn,
        }}
      >
        <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between'}}>
          <div style={{fontSize: 23, fontWeight: 750}}>Codex</div>
          <div style={{display: 'flex', gap: 9}}>
            <span style={{width: 12, height: 12, borderRadius: 99, background: '#d6dde1'}} />
            <span style={{width: 12, height: 12, borderRadius: 99, background: '#d6dde1'}} />
            <span style={{width: 12, height: 12, borderRadius: 99, background: '#d6dde1'}} />
          </div>
        </div>
        <div
          style={{
            marginTop: 45,
            minHeight: 145,
            padding: '28px 30px',
            background: '#f7f9fa',
            border: `1px solid ${COLORS.line}`,
            borderRadius: 18,
            fontSize: 31,
            lineHeight: 1.45,
          }}
        >
          <span
            style={{
              display: 'inline-block',
              color: COLORS.blueStrong,
              background: COLORS.blueSoft,
              padding: '4px 11px',
              borderRadius: 9,
              marginRight: 10,
              fontWeight: 800,
            }}
          >
            $calendly-availability
          </span>
          {typed}
          {frame < 140 ? <span style={{color: COLORS.blue, opacity: frame % 20 < 10 ? 1 : 0}}>▋</span> : null}
        </div>
        <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 28}}>
          <span style={{fontSize: 20, color: COLORS.muted}}>A reusable workflow, invoked by name.</span>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '13px 22px',
              borderRadius: 12,
              background: COLORS.ink,
              color: COLORS.white,
              fontWeight: 750,
              fontSize: 20,
              transform: `scale(${1 - sent * 0.05})`,
            }}
          >
            Run <span style={{fontSize: 24}}>↗</span>
          </div>
        </div>
      </div>
    </Scene>
  );
};

const FlowNode: React.FC<{
  x: number;
  y: number;
  width: number;
  label: string;
  detail: string;
  progress: number;
  accent?: boolean;
}> = ({x, y, width, label, detail, progress, accent = false}) => (
  <div
    style={{
      position: 'absolute',
      left: x,
      top: y,
      width,
      padding: '27px 30px',
      borderRadius: 18,
      border: `1px solid ${accent ? 'rgba(114,173,208,0.65)' : 'rgba(255,255,255,0.15)'}`,
      background: accent ? 'linear-gradient(145deg, #20475c, #173342)' : COLORS.nightRaised,
      boxShadow: '0 28px 70px rgba(0,0,0,0.24)',
      opacity: progress,
      transform: `translateY(${(1 - progress) * 30}px) scale(${0.96 + progress * 0.04})`,
    }}
  >
    <div style={{fontSize: 27, fontWeight: 760}}>{label}</div>
    <div style={{fontSize: 19, color: '#a8b6bd', marginTop: 9}}>{detail}</div>
  </div>
);

const OrchestrationScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = (delay: number) => spring({fps, frame: frame - delay, config: {damping: 20, stiffness: 120}});
  const line = interpolate(frame, [65, 135], [0, 1], clamp);
  return (
    <Scene duration={210}>
      <GridGlow />
      <div style={{position: 'absolute', left: 110, top: 80}}>
        <Kicker>What the skill does</Kicker>
        <div style={{fontSize: 66, fontWeight: 750, letterSpacing: '-0.045em', marginTop: 22}}>
          AI coordinates. Code does the calendar math.
        </div>
      </div>
      <svg style={{position: 'absolute', inset: 0}} width="1920" height="1080" viewBox="0 0 1920 1080">
        <path d="M500 430 C720 430 720 540 860 540" fill="none" stroke="#72add0" strokeWidth="4" strokeDasharray="620" strokeDashoffset={620 * (1 - line)} />
        <path d="M500 720 C720 720 720 585 860 585" fill="none" stroke="#72add0" strokeWidth="4" strokeDasharray="620" strokeDashoffset={620 * (1 - line)} />
        <path d="M1185 560 C1360 560 1360 560 1450 560" fill="none" stroke="#72add0" strokeWidth="4" strokeDasharray="390" strokeDashoffset={390 * (1 - line)} />
      </svg>
      <FlowNode x={130} y={350} width={370} label="Public Calendly" detail="8 booking links" progress={p(18)} />
      <FlowNode x={130} y={650} width={370} label="My calendar" detail="title · start · end" progress={p(40)} />
      <FlowNode x={805} y={465} width={380} label="$calendly-availability" detail="launch · fetch · merge · overlay" progress={p(64)} accent />
      <FlowNode x={1450} y={465} width={350} label="Local calendar" detail="one conflict-aware view" progress={p(100)} />
      <div
        style={{
          position: 'absolute',
          left: 735,
          bottom: 115,
          display: 'flex',
          gap: 22,
          color: '#a9b8c0',
          fontSize: 20,
          opacity: interpolate(frame, [125, 150], [0, 1], clamp),
        }}
      >
        <span>✓ deterministic collection</span>
        <span>✓ provider-agnostic overlay</span>
        <span>✓ loopback-only server</span>
      </div>
    </Scene>
  );
};

const BrowserFrame: React.FC<{
  image: string;
  style?: CSSProperties;
  imageStyle?: CSSProperties;
}> = ({image, style, imageStyle}) => (
  <div
    style={{
      position: 'absolute',
      left: 190,
      top: 52,
      width: 1540,
      height: 975,
      borderRadius: 22,
      overflow: 'hidden',
      background: COLORS.white,
      boxShadow: '0 42px 130px rgba(0,0,0,0.34)',
      border: '1px solid rgba(255,255,255,0.16)',
      ...style,
    }}
  >
    <div
      style={{
        height: 52,
        display: 'flex',
        alignItems: 'center',
        padding: '0 20px',
        background: '#e9edef',
        borderBottom: `1px solid ${COLORS.line}`,
      }}
    >
      <div style={{display: 'flex', gap: 8}}>
        <span style={{width: 12, height: 12, borderRadius: 99, background: '#ff6b62'}} />
        <span style={{width: 12, height: 12, borderRadius: 99, background: '#f5be4f'}} />
        <span style={{width: 12, height: 12, borderRadius: 99, background: '#62c454'}} />
      </div>
      <div
        style={{
          margin: '0 auto',
          width: 640,
          height: 30,
          borderRadius: 8,
          background: '#f9fbfb',
          color: '#7b878e',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          fontSize: 14,
        }}
      >
        127.0.0.1 · Availability calendar
      </div>
      <div style={{width: 68}} />
    </div>
    <Img
      src={staticFile(image)}
      style={{width: '100%', height: 923, objectFit: 'cover', objectPosition: 'top', ...imageStyle}}
    />
  </div>
);

const CalendarScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const reveal = spring({fps, frame: frame - 15, config: {damping: 18, stiffness: 95}});
  const overlay = interpolate(frame, [135, 160], [0, 1], clamp);
  const x = interpolate(frame, [70, 125], [1290, 1500], clamp);
  const y = interpolate(frame, [70, 125], [650, 165], clamp);
  const click = interpolate(frame, [122, 128, 138], [0, 1, 0], clamp);
  return (
    <Scene duration={300}>
      <GridGlow />
      <BrowserFrame
        image="captures/calendar-no-overlay.png"
        style={{
          transform: `translateY(${(1 - reveal) * 80}px) scale(${0.94 + reveal * 0.06})`,
          opacity: reveal,
        }}
      />
      <BrowserFrame image="captures/calendar.png" style={{opacity: overlay}} />
      <div
        style={{
          position: 'absolute',
          left: 82,
          top: 70,
          padding: '18px 24px',
          borderRadius: 14,
          background: COLORS.ink,
          boxShadow: '0 18px 60px rgba(0,0,0,0.25)',
          fontSize: 26,
          fontWeight: 760,
        }}
      >
        {frame < 130 ? '8 links → 1 calendar' : 'Now overlay my calendar'}
      </div>
      <Cursor x={x} y={y} click={click} />
      <div
        style={{
          position: 'absolute',
          bottom: 36,
          left: 650,
          right: 650,
          textAlign: 'center',
          padding: '12px 18px',
          borderRadius: 99,
          background: 'rgba(11,18,22,0.9)',
          fontSize: 20,
          fontWeight: 650,
        }}
      >
        {frame < 135 ? 'Eight links, collapsed into one week.' : 'See the overlap. Choose knowingly.'}
      </div>
    </Scene>
  );
};

const ChoiceScene: React.FC = () => {
  const frame = useCurrentFrame();
  const filtered = interpolate(frame, [122, 142], [0, 1], clamp);
  const zoom = interpolate(frame, [0, 80], [1, 1.06], clamp);
  const translateX = interpolate(frame, [0, 80], [0, -55], clamp);
  const cursorX = interpolate(frame, [25, 105, 190, 245], [1180, 1600, 1600, 1680], clamp);
  const cursorY = interpolate(frame, [25, 105, 190, 245], [660, 220, 220, 470], clamp);
  const click = Math.max(
    interpolate(frame, [103, 109, 120], [0, 1, 0], clamp),
    interpolate(frame, [240, 246, 257], [0, 1, 0], clamp),
  );
  return (
    <Scene duration={300}>
      <GridGlow />
      <BrowserFrame image="captures/drawer-any.png" style={{transform: `translateX(${translateX}px) scale(${zoom})`}} />
      <BrowserFrame
        image="captures/drawer-45.png"
        style={{transform: `translateX(${translateX}px) scale(${zoom})`, opacity: filtered}}
      />
      <div
        style={{
          position: 'absolute',
          left: 90,
          top: 74,
          width: 420,
          padding: '22px 25px',
          borderRadius: 16,
          background: COLORS.ink,
          boxShadow: '0 18px 60px rgba(0,0,0,0.3)',
        }}
      >
        <div style={{fontSize: 17, color: '#9ac9e2', fontWeight: 800, letterSpacing: '0.11em'}}>MAKE THE CHOICE</div>
        <div style={{fontSize: 31, fontWeight: 750, lineHeight: 1.16, marginTop: 12}}>
          {frame < 135 ? 'Filter to the meeting length you need.' : 'Keep every valid 45-minute start.'}
        </div>
      </div>
      <Cursor x={cursorX} y={cursorY} click={click} />
    </Scene>
  );
};

const ThesisScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const lines = [
    ['AI orchestrates.', COLORS.white],
    ['The CLI stays deterministic.', '#9ac9e2'],
    ['The overlay stays local + temporary.', '#f0c58b'],
  ];
  return (
    <Scene duration={180}>
      <GridGlow />
      <div style={{position: 'absolute', left: 190, top: 205, right: 160}}>
        <Kicker>Designed boundary</Kicker>
        <div style={{marginTop: 55}}>
          {lines.map(([line, color], index) => {
            const enter = spring({fps, frame: frame - 20 - index * 28, config: {damping: 20, stiffness: 110}});
            return (
              <div
                key={line}
                style={{
                  color,
                  fontSize: 78,
                  fontWeight: 750,
                  letterSpacing: '-0.045em',
                  lineHeight: 1.25,
                  opacity: enter,
                  transform: `translateX(${(1 - enter) * 80}px)`,
                }}
              >
                {line}
              </div>
            );
          })}
        </div>
        <div
          style={{
            marginTop: 55,
            display: 'flex',
            gap: 14,
            opacity: interpolate(frame, [110, 140], [0, 1], clamp),
          }}
        >
          {['Loopback-only', 'No credentials in the app', 'No committed calendar data'].map((item) => (
            <span key={item} style={{padding: '12px 17px', borderRadius: 99, border: '1px solid rgba(255,255,255,0.2)', color: '#b7c3c9', fontSize: 18}}>
              {item}
            </span>
          ))}
        </div>
      </div>
    </Scene>
  );
};

const EndScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({fps, frame: frame - 8, config: {damping: 18, stiffness: 100}});
  const underline = interpolate(frame, [65, 125], [0, 1], clamp);
  return (
    <Scene duration={180} background={COLORS.blueStrong}>
      <AbsoluteFill
        style={{
          backgroundImage: 'radial-gradient(circle at 50% 20%, rgba(255,255,255,0.16), transparent 38%)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          transform: `translateY(${(1 - enter) * 55}px)`,
          opacity: enter,
        }}
      >
        <div style={{fontSize: 24, fontWeight: 850, letterSpacing: '0.15em', textTransform: 'uppercase', color: '#c9e6f4'}}>
          $calendly-availability
        </div>
        <div style={{fontSize: 105, lineHeight: 1, fontWeight: 780, letterSpacing: '-0.065em', marginTop: 36}}>
          One prompt. One calendar.
        </div>
        <div style={{fontSize: 42, fontWeight: 680, color: '#d9edf6', marginTop: 26}}>No tab roulette.</div>
        <div
          style={{
            marginTop: 74,
            fontFamily: 'SFMono-Regular, Menlo, Consolas, monospace',
            fontSize: 25,
            paddingBottom: 12,
            position: 'relative',
          }}
        >
          github.com/justinobney/calendly-availability
          <span
            style={{
              position: 'absolute',
              left: 0,
              right: `${(1 - underline) * 100}%`,
              bottom: 0,
              height: 3,
              borderRadius: 4,
              background: '#c9e6f4',
            }}
          />
        </div>
      </div>
    </Scene>
  );
};

export const SkillLaunch: React.FC = () => {
  return (
    <AbsoluteFill style={{background: COLORS.night}}>
      <Sequence from={0} durationInFrames={240} name="Pain">
        <PainScene />
      </Sequence>
      <Sequence from={240} durationInFrames={210} name="Prompt">
        <PromptScene />
      </Sequence>
      <Sequence from={450} durationInFrames={210} name="Orchestration">
        <OrchestrationScene />
      </Sequence>
      <Sequence from={660} durationInFrames={300} name="Unified calendar">
        <CalendarScene />
      </Sequence>
      <Sequence from={960} durationInFrames={300} name="Length and choices">
        <ChoiceScene />
      </Sequence>
      <Sequence from={1260} durationInFrames={180} name="Boundary">
        <ThesisScene />
      </Sequence>
      <Sequence from={1440} durationInFrames={180} name="End card">
        <EndScene />
      </Sequence>
    </AbsoluteFill>
  );
};
