// Hand-drawn SVG graphics (no chart library): the prediction gauge and the pitches.
import type { Position, Prediction } from "../api/types";
import { fixed, gapVerdict, gaugeAngle, gaugeMax, POSITION_NAMES, signed } from "../lib/format";
import { DownIcon, LevelIcon, UpIcon } from "./icons";

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const a = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.sin(a), y: cy - r * Math.cos(a) };
}

function arc(cx: number, cy: number, r: number, from: number, to: number) {
  const a = polar(cx, cy, r, from);
  const b = polar(cx, cy, r, to);
  return `M${a.x.toFixed(2)} ${a.y.toFixed(2)}A${r} ${r} 0 0 1 ${b.x.toFixed(2)} ${b.y.toFixed(2)}`;
}

/**
 * Predicted vs actual non-penalty G+A per 90 on a half-circle gauge.
 * The filled arc is what the player actually produced; the cyan needle is what
 * the model expected from how the player plays.
 */
export function PredictionGauge({ prediction, typicalError }: { prediction: Prediction; typicalError: number }) {
  const { predictedP90: predicted, actualP90: actual, gapP90: gap } = prediction;
  const max = gaugeMax(predicted, actual);
  const cx = 100, cy = 100, r = 78;
  const actualAngle = gaugeAngle(actual, max);
  const needle = polar(cx, cy, r + 8, gaugeAngle(predicted, max));
  const needleBase = polar(cx, cy, r - 16, gaugeAngle(predicted, max));
  const verdict = gapVerdict(gap, typicalError);
  const tone = verdict === "under" ? "var(--magenta)" : "var(--green)";
  const Icon = verdict === "over" ? UpIcon : verdict === "under" ? DownIcon : LevelIcon;
  const ticks = [0, max / 2, max];

  return (
    <figure style={{ margin: 0 }}>
      <svg className="gauge" viewBox="0 0 200 124" role="img"
        aria-label={`Actual ${fixed(actual)} against predicted ${fixed(predicted)} non-penalty goals plus assists per 90, a gap of ${signed(gap)}.`}>
        <path d={arc(cx, cy, r, -90, 90)} stroke="var(--line)" strokeWidth="12" fill="none" strokeLinecap="round" />
        {actual > 0 && (
          <path d={arc(cx, cy, r, -90, actualAngle)} stroke={tone} strokeWidth="12" fill="none" strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 4px ${verdict === "under" ? "var(--glow-magenta)" : "var(--glow-green)"})` }} />
        )}
        <line x1={needleBase.x} y1={needleBase.y} x2={needle.x} y2={needle.y} stroke="var(--cyan)" strokeWidth="3"
          strokeLinecap="round" style={{ filter: "drop-shadow(0 0 3px var(--glow-cyan))" }} />
        {ticks.map((t) => {
          const p = polar(cx, cy, r + 17, gaugeAngle(t, max));
          return (
            <text key={t} x={p.x} y={p.y + 3} textAnchor="middle" fontSize="9" fill="var(--text-3)" className="num">
              {t.toFixed(1)}
            </text>
          );
        })}
        <text x={cx} y={cy - 14} textAnchor="middle" fontSize="30" fontWeight="700" fill="var(--text)" className="num">
          {fixed(actual)}
        </text>
        <text x={cx} y={cy + 4} textAnchor="middle" fontSize="8.5" fill="var(--text-3)" letterSpacing="1.5">
          ACTUAL PER 90
        </text>
      </svg>
      <figcaption>
        <div className="gauge-legend">
          <span className="key" style={{ color: tone }}><i /><span style={{ color: "var(--text-2)" }}>Actual <b className="num">{fixed(actual)}</b></span></span>
          <span className="key" style={{ color: "var(--cyan)" }}><i /><span style={{ color: "var(--text-2)" }}>Predicted <b className="num">{fixed(predicted)}</b></span></span>
          <span className={`verdict verdict--${verdict}`}>
            <Icon size={13} />
            <span className="num">{signed(gap)}</span>
            {verdict === "over" ? "Over-performing" : verdict === "under" ? "Under-performing" : "In line with the model"}
          </span>
        </div>
      </figcaption>
    </figure>
  );
}

const ZONES: Record<Position, { x: number; y: number; w: number; h: number }[]> = {
  GKP: [{ x: 24, y: 92, w: 20, h: 9 }],
  DEF: [{ x: 6, y: 70, w: 56, h: 18 }],
  MID: [{ x: 10, y: 43, w: 48, h: 22 }],
  WNG: [{ x: 3, y: 18, w: 14, h: 30 }, { x: 51, y: 18, w: 14, h: 30 }],
  STR: [{ x: 22, y: 8, w: 24, h: 18 }],
};

/** Outline of a pitch, attacking upwards, in a 68 x 105 box. */
export function PitchLines() {
  return (
    <g className="pitch-lines">
      <rect x="1" y="1" width="66" height="103" />
      <path d="M1 52.5h66" />
      <circle cx="34" cy="52.5" r="9.15" />
      <rect x="13.85" y="1" width="40.3" height="16.5" />
      <rect x="24.85" y="1" width="18.3" height="5.5" />
      <rect x="13.85" y="87.5" width="40.3" height="16.5" />
      <rect x="24.85" y="98.5" width="18.3" height="5.5" />
    </g>
  );
}

/** Where the player's position sits on the pitch. */
export function MiniPitch({ position, role }: { position: Position; role: string }) {
  return (
    <figure style={{ margin: 0 }}>
      <svg className="mini-pitch" viewBox="0 0 68 105" role="img"
        aria-label={`${POSITION_NAMES[position]} (${role}), shown on a pitch attacking upwards`}>
        <PitchLines />
        {ZONES[position].map((z, i) => (
          <rect key={i} className="pitch-zone" x={z.x} y={z.y} width={z.w} height={z.h} rx="1.5" />
        ))}
      </svg>
      <figcaption className="note" style={{ textAlign: "center" }}>
        {POSITION_NAMES[position]} · {role} · attacking upwards
      </figcaption>
    </figure>
  );
}
