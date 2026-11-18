/** The page background: a faint tactical-board grid with a full pitch drawn over it. */
export function PitchBackground() {
  return (
    <svg className="pitch-bg" aria-hidden="true" focusable="false" preserveAspectRatio="xMidYMid slice"
      viewBox="0 0 1600 1000">
      <defs>
        <pattern id="pitch-grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path className="grid" d="M40 0H0V40" fill="none" strokeWidth="1" />
        </pattern>
      </defs>
      <rect width="1600" height="1000" fill="url(#pitch-grid)" />
      <g className="lines" fill="none" strokeWidth="1.5">
        <rect x="120" y="80" width="1360" height="840" />
        <path d="M800 80v840" />
        <circle cx="800" cy="500" r="110" />
        <circle cx="800" cy="500" r="3" />
        <rect x="120" y="290" width="200" height="420" />
        <rect x="120" y="400" width="70" height="200" />
        <rect x="1280" y="290" width="200" height="420" />
        <rect x="1410" y="400" width="70" height="200" />
        <path d="M320 425a110 110 0 0 1 0 150M1280 425a110 110 0 0 0 0 150" />
      </g>
    </svg>
  );
}
