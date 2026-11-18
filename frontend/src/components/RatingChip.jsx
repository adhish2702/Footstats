/** Rating number with a small bar showing distance from the average (50). */
export default function RatingChip({ value, muted = false }) {
  if (value === null || value === undefined) return <span className="chip">–</span>;
  const above = value >= 50;
  const width = Math.min(Math.abs(value - 50) * 2, 50); // 25 points either side = full half
  return (
    <span
      className={`chip${muted ? " is-muted" : ""}`}
      title={muted ? "Under 900 minutes: rating pulled toward average" : undefined}
    >
      <span className="chip-track" aria-hidden="true">
        <span
          className={`chip-fill ${above ? "up" : "down"}`}
          style={above ? { left: "50%", width: `${width}%` } : { right: "50%", width: `${width}%` }}
        />
      </span>
      <span className="chip-num">{value.toFixed(1)}</span>
    </span>
  );
}
