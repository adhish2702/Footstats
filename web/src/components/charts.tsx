import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip } from "recharts";
import type { StyleFeature } from "../api/types";
import { fixed, ordinal } from "../lib/format";

/** The eight features shown on the radar: a spread of shooting, creating, carrying and winning the ball. */
export const RADAR_KEYS = [
  "shots_p90",
  "touches_in_box_p90",
  "shot_creating_actions_p90",
  "key_passes_p90",
  "progressive_passes_p90",
  "progressive_carries_p90",
  "successful_take_ons_p90",
  "ball_recoveries_p90",
] as const;

const SHORT_LABELS: Record<string, string> = {
  shots_p90: "Shots",
  touches_in_box_p90: "Box touches",
  shot_creating_actions_p90: "Shot creation",
  key_passes_p90: "Key passes",
  progressive_passes_p90: "Prog. passes",
  progressive_carries_p90: "Prog. carries",
  successful_take_ons_p90: "Take-ons",
  ball_recoveries_p90: "Recoveries",
};

/** Compare series: fixed order, never cycled. Each also has its own line style and marker. */
export const SERIES = [
  { color: "var(--green)", dash: undefined, marker: "circle" },
  { color: "var(--cyan)", dash: "6 4", marker: "square" },
  { color: "var(--neutral-series)", dash: "2 3", marker: "diamond" },
] as const;

type Marker = (typeof SERIES)[number]["marker"];

function MarkerShape({ cx, cy, marker, color }: { cx?: number; cy?: number; marker: Marker; color: string }) {
  if (cx === undefined || cy === undefined) return null;
  const s = 4;
  if (marker === "square") return <rect x={cx - s} y={cy - s} width={s * 2} height={s * 2} fill={color} stroke="var(--bg)" strokeWidth={2} />;
  if (marker === "diamond") {
    return <path d={`M${cx} ${cy - s - 1}L${cx + s + 1} ${cy}L${cx} ${cy + s + 1}L${cx - s - 1} ${cy}Z`} fill={color} stroke="var(--bg)" strokeWidth={2} />;
  }
  return <circle cx={cx} cy={cy} r={s} fill={color} stroke="var(--bg)" strokeWidth={2} />;
}

export interface RadarSeries {
  name: string;
  features: StyleFeature[];
}

interface RadarRow {
  key: string;
  label: string;
  full: string;
  [series: string]: number | string | null;
}

function radarRows(series: RadarSeries[]): RadarRow[] {
  return RADAR_KEYS.map((key) => {
    const row: RadarRow = { key, label: SHORT_LABELS[key] ?? key, full: "" };
    series.forEach((s, i) => {
      const f = s.features.find((x) => x.key === key);
      row.full = f?.label ?? key;
      row[`p${i}`] = f?.percentile ?? 0;
      row[`v${i}`] = f?.value ?? null;
    });
    return row;
  });
}

function RadarTooltip({ active, payload, series }: { active?: boolean; payload?: { payload: RadarRow }[]; series: RadarSeries[] }) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  return (
    <div className="chart-tooltip">
      <strong>{row.full}</strong>
      {series.map((s, i) => (
        <div key={s.name}>
          {series.length > 1 && <span>{s.name}: </span>}
          <span className="num">{fixed(row[`v${i}`] as number | null)}</span> per 90 ·{" "}
          <span className="num">{ordinal(row[`p${i}`] as number)}</span> percentile
        </div>
      ))}
    </div>
  );
}

/**
 * Playing-style radar: each spoke is a percentile (0-100) among qualified
 * players in the same position. One series on a profile, up to three on compare.
 */
export function StyleRadar({ series, label }: { series: RadarSeries[]; label: string }) {
  const rows = radarRows(series);
  const compare = series.length > 1;
  return (
    <div className={`radar ${compare ? "radar--compare" : ""}`} role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={rows} outerRadius="72%" margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
          <PolarGrid stroke="var(--chart-grid)" />
          <PolarAngleAxis dataKey="label" tick={{ fill: "var(--text-2)", fontSize: 12, fontFamily: "var(--font-body)" }} />
          <PolarRadiusAxis domain={[0, 100]} tickCount={5} tick={false} axisLine={false} />
          {series.map((s, i) => {
            const style = SERIES[i]!;
            return (
              <Radar
                key={s.name}
                name={s.name}
                dataKey={`p${i}`}
                stroke={style.color}
                strokeWidth={2}
                strokeDasharray={style.dash}
                fill={style.color}
                fillOpacity={compare ? 0.06 : 0.16}
                dot={(props: { cx?: number; cy?: number; index?: number }) => (
                  <MarkerShape key={`${i}-${props.index}`} cx={props.cx} cy={props.cy} marker={style.marker} color={style.color} />
                )}
                isAnimationActive={false}
              />
            );
          })}
          <Tooltip content={<RadarTooltip series={series} />} cursor={false} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Legend for the compare radar: swatch, line style, marker and name. */
export function SeriesLegend({ names }: { names: string[] }) {
  return (
    <div className="legend" aria-label="Legend">
      {names.map((name, i) => {
        const s = SERIES[i]!;
        return (
          <span key={name} className="key">
            <svg width="34" height="12" aria-hidden="true">
              <line x1="1" y1="6" x2="33" y2="6" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} />
              <MarkerShape cx={17} cy={6} marker={s.marker} color={s.color} />
            </svg>
            {name}
          </span>
        );
      })}
    </div>
  );
}
