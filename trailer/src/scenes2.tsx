import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, staticFile, useVideoConfig} from 'remotion';
import {BAR, BEAT, C, F} from './theme';
import {At, Brand, Chip, Clip, Count, Flash, Mode, Slam, VoxelBG, clamp01, clipStart, easeOut, fmtInt, pulse, useT, useTall} from './components';
import {byId} from './scenes1';

const gridFor = (n: number, W: number, H: number) => {
  const cols = Math.ceil(Math.sqrt((n * W) / H));
  const rows = Math.ceil(n / cols);
  return {cols, rows, tw: W / cols, th: H / rows};
};

// ---------- 4. Build: tiles multiply on every beat, text on every bar, blackout on the last beat ----------
const BUILD_TEXT_WIDE = ['One brain.', '23 PvP modes.', 'Duels. Bed Wars. SkyWars.', 'The Bridge. UHC. Spleef.', 'TNT Run. Parkour.', 'Survival.', 'All at once.', 'Ready?'];
const BUILD_TEXT_TALL = ['One brain.', '23 PvP modes.'];
export const Build: React.FC<{P: any; dur: number}> = ({P, dur}) => {
  const t = useT();
  const tall = useTall();
  const {width, height} = useVideoConfig();
  const nb = Math.round(dur / BEAT);
  const b = Math.min(nb - 1, Math.floor(t / BEAT));
  const n = Math.min(23, 1 + Math.floor(Math.pow(b / (nb - 1), 1.7) * 22));
  const order: Mode[] = Array.from({length: 23}, (_, i) => P.modes[(i * 7) % P.modes.length]);
  const {cols, rows, tw, th} = gridFor(n, width, height);
  const bi = Math.floor(t / BAR);
  const texts = tall ? BUILD_TEXT_TALL : BUILD_TEXT_WIDE;
  const blackout = t > dur - BEAT;
  return (
    <AbsoluteFill style={{background: C.bg}}>
      {order.slice(0, n).map((m, i) => {
        const r = Math.floor(i / cols);
        const inRow = r === rows - 1 ? n - (rows - 1) * cols : cols;
        const off = ((cols - inRow) * tw) / 2;
        return (
          <Clip
            key={m.id}
            m={m}
            start={clipStart(m, i)}
            label={tw > 300}
            punch={false}
            style={{left: (i % cols) * tw + (r === rows - 1 ? off : 0) + 2, top: r * th + 2, width: tw - 4, height: th - 4}}
          />
        );
      })}
      <div style={{position: 'absolute', left: 0, right: 0, top: '50%', transform: 'translateY(-50%)', padding: '0 60px', display: 'flex', justifyContent: 'center'}}>
        {texts.map((tx, i) =>
          i === bi ? (
            <Slam key={i} at={i * BAR} align="center" size={tall ? 130 : 150} style={{textShadow: '0 4px 30px #000, 0 0 12px #000, 0 0 3px #000'}}>
              {tx}
            </Slam>
          ) : null
        )}
      </div>
      <div style={{position: 'absolute', right: 40, top: 30}}>
        <Chip size={tall ? 24 : 26} solid>{n} / 23 modes</Chip>
      </div>
      {blackout && (
        <AbsoluteFill style={{background: C.bg, justifyContent: 'center', alignItems: 'center'}}>
          <div style={{width: `${easeOut((t - (dur - BEAT)) / BEAT) * 70}%`, height: 6, background: C.accent, boxShadow: `0 0 40px ${C.accent}`}} />
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

// ---------- 5. Drop: the 23-mode wall, then hero cuts and split screens ----------
const HEROES = ['duels_sword', 'bedwars_squads', 'skywars_solo', 'the_bridge', 'kitpvp', 'tnt_run', 'spleef', 'parkour_duel'];
const Wall: React.FC<{P: any}> = ({P}) => {
  const t = useT();
  const tall = useTall();
  const cols = tall ? 3 : 6;
  const tw = tall ? 360 : 320;
  const th = tall ? 202.5 : 180;
  const top = tall ? 150 : 180;
  const idx = Math.floor(t / (BEAT / 2)) % 23;
  const m = P.modes[idx];
  const W = cols * tw;
  const H = (tall ? 8 : 4) * th;
  const p = pulse(t, 5);
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <div style={{position: 'absolute', left: 0, top, width: W, height: H, overflow: 'hidden'}}>
        <OffthreadVideo src={staticFile(tall ? 'wallv.mp4' : 'wall.mp4')} muted style={{width: W, height: H, objectFit: 'fill', imageRendering: 'pixelated', filter: 'contrast(1.18) saturate(1.3) brightness(0.95)'}} />
        <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(160deg, rgba(124,196,160,0.22), transparent 55%, rgba(126,168,240,0.14))', mixBlendMode: 'screen'}} />
        <div style={{position: 'absolute', inset: 0, backgroundImage: `linear-gradient(90deg, ${C.bg} 3px, transparent 3px), linear-gradient(${C.bg} 3px, transparent 3px)`, backgroundSize: `${tw}px ${th}px`}} />
        <div style={{position: 'absolute', inset: 0, background: C.glow, opacity: 0.1 * p, mixBlendMode: 'screen'}} />
        <div
          style={{
            position: 'absolute', left: (idx % cols) * tw, top: Math.floor(idx / cols) * th, width: tw, height: th,
            border: `5px solid ${C.glow}`, boxShadow: `0 0 40px ${C.accent}, inset 0 0 30px rgba(124,196,160,0.5)`,
          }}
        />
      </div>
      <div style={{position: 'absolute', left: 60, top: tall ? 40 : 40}}>
        <Slam at={0} size={tall ? 74 : 92} glow>23 modes. One network.</Slam>
      </div>
      <div style={{position: 'absolute', left: 60, right: 60, top: top + H + (tall ? 30 : 16), display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap'}}>
        <Chip size={tall ? 36 : 46} solid>{m.name}</Chip>
        <Chip size={tall ? 24 : 30} color={m.wins > 0 ? C.accent : C.bad}>{m.wins}/{m.episodes} wins{m.ret != null ? `  return ${m.ret.toFixed(1)}` : ''}</Chip>
      </div>
    </AbsoluteFill>
  );
};
export const Drop: React.FC<{P: any; dur: number}> = ({P, dur}) => {
  const tall = useTall();
  const {width, height} = useVideoConfig();
  const half = dur / 2;
  const segN = Math.round(half / (BEAT * 2));
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <At from={0} dur={half}>
        <Wall P={P} />
      </At>
      {Array.from({length: segN}, (_, i) => {
        const from = half + i * BEAT * 2;
        const m = byId(P, HEROES[i % HEROES.length]);
        const split = i % 2 === 1;
        const others = [byId(P, HEROES[(i + 3) % 8]), m, byId(P, HEROES[(i + 5) % 8])];
        return (
          <At key={i} from={from} dur={BEAT * 2}>
            {split ? (
              others.map((o, j) => {
                const w = tall ? width : width / 3;
                const h = tall ? height / 3 : height;
                return <Clip key={j} m={o} start={clipStart(o, i + j * 4)} big={false} style={{left: tall ? 0 : j * w + 2, top: tall ? j * h + 2 : 0, width: w - (tall ? 0 : 4), height: h - (tall ? 4 : 0)}} />;
              })
            ) : (
              <>
                <Clip m={m} start={clipStart(m, i)} big style={{left: 0, top: 0, width, height}} />
                <div style={{position: 'absolute', left: 50, top: tall ? 120 : 60, maxWidth: width - 100}}>
                  <Slam at={0} size={tall ? 110 : 150} style={{textShadow: '0 4px 24px #000'}}>{m.name}</Slam>
                </div>
              </>
            )}
            <Flash at={0} strength={0.4} dur={0.2} />
          </At>
        );
      })}
    </AbsoluteFill>
  );
};

// ---------- 6. Cloud: 12 workers, federated averaging, evaluation ----------
const short = (id: string) => id.replace(/_/g, ' ');
export const Cloud: React.FC<{P: any}> = ({P}) => {
  const t = useT();
  const tall = useTall();
  const ws: any[] = P.stats.workers.length ? P.stats.workers : Array.from({length: 12}, (_, i) => ({job: `w${i + 1}`, modes: [], steps: 0}));
  const cols = tall ? 3 : 4;
  const cw = tall ? 300 : 230;
  const ch = tall ? 118 : 130;
  const gx = 18;
  const x0 = tall ? 60 : 140;
  const y0 = tall ? 430 : 300;
  const pos = (i: number) => ({x: x0 + (i % cols) * (cw + gx), y: y0 + Math.floor(i / cols) * (ch + gx)});
  const gridBottom = y0 + 3 * (ch + gx);
  const fx = tall ? 60 : 1240;
  const fy = tall ? gridBottom + 20 : 300;
  const fw = tall ? 960 : 540;
  const showFed = t > BEAT * 12;
  const showEval = t > BEAT * 14;
  return (
    <AbsoluteFill>
      <VoxelBG dim={0.7} />
      <div style={{position: 'absolute', left: x0, top: tall ? 90 : 90, right: 60}}>
        <Slam at={0} size={tall ? 92 : 96}>{tall ? 'Trained in the cloud.' : 'The cloud does the training.'}</Slam>
        <Slam at={BEAT} size={tall ? 28 : 32} mono color={C.accent} style={{marginTop: 14}}>12 workers a round / 2 modes each / free GitHub Actions</Slam>
      </div>
      {ws.slice(0, 12).map((w, i) => {
        const on = t > BEAT * i;
        const fresh = on ? pulse(t - BEAT * i, 3) : 0;
        const p = pos(i);
        return (
          <div
            key={i}
            style={{
              position: 'absolute', left: p.x, top: p.y, width: cw, height: ch, background: 'rgba(18,23,32,0.92)',
              border: `2px solid ${on ? C.accent : C.line}`, opacity: on ? 1 : 0.35, padding: 12,
              boxShadow: on ? `0 0 ${20 + 40 * fresh}px rgba(124,196,160,${0.15 + 0.5 * fresh})` : 'none',
              fontFamily: F.mono, color: C.muted, fontSize: tall ? 17 : 18, lineHeight: 1.3, overflow: 'hidden',
            }}
          >
            <div style={{fontWeight: 700, color: on ? C.accent : C.muted, fontSize: tall ? 24 : 26}}>W{String(i + 1).padStart(2, '0')}</div>
            <div>{(w.modes || []).map(short).join(' + ')}</div>
            {w.steps > 0 && <div style={{color: C.text}}>{fmtInt(w.steps)} steps</div>}
          </div>
        );
      })}
      {showFed && (
        <div style={{position: 'absolute', left: fx, top: fy, width: fw, padding: 22, background: 'rgba(18,23,32,0.95)', border: `4px solid ${C.accent}`, boxShadow: `0 0 50px rgba(124,196,160,${0.3 + 0.3 * pulse(t, 4)})`}}>
          <div style={{fontFamily: F.head, fontWeight: 700, fontSize: tall ? 48 : 54, color: C.text, letterSpacing: -1}}>FEDERATED AVERAGING</div>
          <div style={{fontFamily: F.mono, fontSize: 24, color: C.muted}}>12 workers merge into one network</div>
        </div>
      )}
      {showEval && (
        <div style={{position: 'absolute', left: fx, top: fy + (tall ? 150 : 170), width: fw, padding: 22, background: 'rgba(18,23,32,0.95)', border: `2px solid ${C.blue}`}}>
          <div style={{fontFamily: F.head, fontWeight: 700, fontSize: tall ? 42 : 46, color: C.text, letterSpacing: -1}}>EVALUATE ALL 23 MODES</div>
          <div style={{fontFamily: F.mono, fontSize: 24, color: C.muted}}>win rate + gameplay clips, every round</div>
        </div>
      )}
      {P.stats.steps > 0 && t > BEAT * 8 && (
        <div style={{position: 'absolute', left: fx, top: tall ? fy + 330 : fy + 360, width: fw}}>
          <Count to={P.stats.steps} at={BEAT * 8} dur={2} size={tall ? 90 : 100} color={C.glow} />
          <div style={{fontFamily: F.mono, fontSize: 24, color: C.muted}}>game steps trained so far, in MineStudio (Minecraft 1.16.5), against armed mobs in sky arenas</div>
        </div>
      )}
      <Flash at={0} strength={0.3} />
    </AbsoluteFill>
  );
};

// ---------- 7. Dashboard fly-through + round timeline (wide only) ----------
const SHOTS = [
  {k: 'overview', h: 'The whole project'},
  {k: 'dashboard', h: 'Live training'},
  {k: 'simulate', h: 'Design your own arena'},
  {k: 'live', h: 'Watch it play'},
];
export const Dash: React.FC<{P: any}> = ({P}) => {
  const t = useT();
  const bi = Math.min(3, Math.floor(t / BAR));
  const u = clamp01((t - bi * BAR) / BAR);
  const w = 1120;
  const h = 700;
  const rounds: any[] = P.stats.rounds;
  const slots = Math.max(5, rounds.length + 2);
  const lx0 = 200;
  const lx1 = 1720;
  const lineP = easeOut(t / 2.5);
  return (
    <AbsoluteFill>
      <VoxelBG dim={0.8} floor={false} />
      <div style={{position: 'absolute', left: 90, top: 56}}>
        <Slam at={0} size={70}>Round by round.</Slam>
      </div>
      <div style={{position: 'absolute', right: 90, top: 70}}>
        {SHOTS.map((s, i) => (i === bi ? <Slam key={s.k} at={i * BAR} size={44} mono color={C.accent} align="right">{s.h}</Slam> : null))}
      </div>
      {SHOTS.map((s, j) => {
        if (j > bi || bi - j > 2 || !P.shots[s.k]) return null;
        const age = bi - j;
        const e = easeOut(age === 0 ? Math.min(1, u * 6) : 1);
        const rotY = age === 0 ? -26 + 22 * u : -10;
        const tx = age === 0 ? 420 * (1 - e) - 60 * u : -330 * age - 60;
        const sc = age === 0 ? 0.9 + 0.12 * u : 0.8 - 0.06 * age;
        return (
          <div
            key={s.k}
            style={{
              position: 'absolute', left: (1920 - w) / 2, top: 150, width: w, height: h, perspective: 1800,
              transform: `translateX(${tx}px)`, opacity: age === 0 ? e : 0.45, zIndex: 10 - age,
            }}
          >
            <div style={{width: w, height: h, transform: `rotateY(${rotY}deg) rotateX(5deg) scale(${sc})`, border: `3px solid ${C.accent}`, boxShadow: `0 0 80px rgba(124,196,160,0.3)`, overflow: 'hidden', background: C.panel}}>
              <Img src={staticFile(P.shots[s.k])} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
              <div style={{position: 'absolute', inset: 0, background: 'repeating-linear-gradient(0deg, rgba(0,0,0,0.12) 0 1px, transparent 1px 3px)'}} />
            </div>
          </div>
        );
      })}
      <div style={{position: 'absolute', left: lx0, top: 940, width: lx1 - lx0, height: 4, background: C.line}} />
      <div style={{position: 'absolute', left: lx0, top: 940, width: (lx1 - lx0) * lineP * Math.min(1, (rounds.length + 0.5) / (slots - 1)), height: 4, background: C.accent}} />
      {Array.from({length: slots}, (_, i) => {
        const r = rounds[i];
        const x = lx0 + ((lx1 - lx0) * i) / (slots - 1);
        const shown = easeOut((t - 0.3 - i * 0.18) / 0.3);
        return (
          <div key={i} style={{position: 'absolute', left: x - 12, top: 930, opacity: shown}}>
            <div style={{width: 24, height: 24, background: r ? C.accent : C.bg, border: `3px solid ${r ? C.glow : C.line}`, boxShadow: r ? `0 0 20px ${C.accent}` : 'none'}} />
            <div style={{position: 'absolute', top: 36, left: -60, width: 144, textAlign: 'center', fontFamily: F.mono, fontSize: 20, color: r ? C.text : C.faint || C.muted, fontWeight: 700}}>
              {r ? r.tag.toUpperCase().replace('-', ' ') : i === rounds.length ? 'TRAINING NOW' : 'NEXT'}
            </div>
            {r && (
              <div style={{position: 'absolute', top: 64, left: -60, width: 144, textAlign: 'center', fontFamily: F.mono, fontSize: 18, color: C.accent}}>
                {r.wins}/{r.games} wins{r.elo ? ` / elo ${Math.round(r.elo)}` : ''}
              </div>
            )}
          </div>
        );
      })}
      {[0, 1, 2, 3].map((i) => (
        <Flash key={i} at={i * BAR} strength={0.22} />
      ))}
    </AbsoluteFill>
  );
};

// ---------- 8. Finale: from 0 wins -> watch it learn live ----------
export const Finale: React.FC<{P: any; dur: number}> = ({P, dur}) => {
  const t = useT();
  const tall = useTall();
  const hitT = tall ? BAR : BAR * 2;
  const {wins, games} = P.stats;
  const img = P.liveFrame || P.shots.live;
  const cw = tall ? 900 : 860;
  const chh = Math.round((cw * 9) / 16);
  const fade = clamp01((dur - t) / (tall ? 0.7 : 1.2));
  return (
    <AbsoluteFill style={{opacity: fade}}>
      <VoxelBG />
      <div style={{position: 'absolute', left: tall ? 60 : 80, top: tall ? 80 : 60}}>
        <Brand size={tall ? 34 : 30} />
      </div>
      {img && t >= (tall ? 0.3 : BAR) && (
        <div
          style={{
            position: 'absolute', right: tall ? 90 : 100, top: tall ? 560 : 200, width: cw, height: chh,
            border: `4px solid ${C.accent}`, boxShadow: `0 0 90px rgba(124,196,160,${0.3 + 0.2 * pulse(t, 4)})`, overflow: 'hidden',
            transform: `translateY(${(1 - easeOut((t - (tall ? 0.3 : BAR)) / 0.4)) * 60}px)`, opacity: easeOut((t - (tall ? 0.3 : BAR)) / 0.3),
          }}
        >
          <Img src={staticFile(img)} style={{width: '100%', height: '100%', objectFit: 'cover', imageRendering: 'pixelated', filter: 'contrast(1.15) saturate(1.2)'}} />
          <div style={{position: 'absolute', inset: 0, background: 'repeating-linear-gradient(0deg, rgba(0,0,0,0.25) 0 1px, transparent 1px 3px)'}} />
        </div>
      )}
      <div style={{position: 'absolute', left: tall ? 60 : 100, top: tall ? 220 : 220, display: 'flex', flexDirection: 'column', gap: 18}}>
        <Slam at={0} size={tall ? 150 : 190} color={C.text}>From</Slam>
        <Slam at={BEAT} size={tall ? 150 : 190} color={C.bad}>{fmtInt(wins)} wins.</Slam>
        {t >= (tall ? 0.8 : BAR) && <Slam at={tall ? 0.8 : BAR} size={tall ? 36 : 36} mono color={C.muted}>{fmtInt(wins)} / {fmtInt(games)} baseline games</Slam>}
      </div>
      {t >= hitT && (
        <div style={{position: 'absolute', left: tall ? 60 : 100, top: tall ? 1180 : 740, display: 'flex', flexDirection: 'column', gap: 18}}>
          <Slam at={hitT} size={tall ? 110 : 120} glow color={C.accent}>Watch it learn live.</Slam>
          <Slam at={hitT + BEAT} size={tall ? 44 : 48} mono color={C.text}>vpt-arena.vercel.app</Slam>
          <Slam at={hitT + BEAT * 2} size={tall ? 24 : 26} mono color={C.muted}>live training / live stream / simulation lab</Slam>
        </div>
      )}
      <Flash at={hitT} strength={0.85} dur={0.5} />
    </AbsoluteFill>
  );
};
