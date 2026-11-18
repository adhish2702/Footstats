import { useNavigate } from "react-router-dom";
import type { PositionGap } from "../api/types";
import { POSITION_NAMES, STATUS_TEXT, initials } from "../lib/format";
import { formationSlots } from "../lib/formation";
import { PitchLines } from "./svg";

const lastName = (name: string) => name.trim().split(/\s+/).at(-1) ?? name;

/**
 * The club's squad as a 4-3-3 seen from above. Each node is a player slot,
 * outlined by how that position compares with the league: green above, grey
 * below, magenta and pulsing when weak or when no qualified player plays there.
 */
export function FormationPitch({ positions, club }: { positions: PositionGap[]; club: string }) {
  const navigate = useNavigate();
  const slots = formationSlots(positions);
  const summary = positions.map((p) => `${POSITION_NAMES[p.position]}: ${STATUS_TEXT[p.status]}`).join("; ");
  // The pitch is 68 x 105; slot coordinates are percentages.
  const X = (x: number) => (x / 100) * 68;
  const Y = (y: number) => (y / 100) * 105;

  return (
    <svg className="formation" viewBox="-2 -2 72 109" role="img" aria-label={`${club} in a 4-3-3. ${summary}.`}>
      <rect className="pitch-surface" x="1" y="1" width="66" height="103" />
      <PitchLines />
      {slots.map((slot, i) => {
        const cx = X(slot.x);
        const cy = Y(slot.y);
        const alarm = slot.status === "weak" || slot.status === "missing";
        const go = slot.player ? () => navigate(`/players/${slot.player!.id}`) : undefined;
        return (
          <g key={i} className={`node node--${slot.status}`} transform={`translate(${cx} ${cy})`}
            style={{ cursor: go ? "pointer" : "default" }} onClick={go}
            onKeyDown={go ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } } : undefined}
            tabIndex={go ? 0 : undefined} role={go ? "link" : undefined}
            aria-label={go ? `${slot.player!.name}, ${POSITION_NAMES[slot.position]}` : undefined}>
            {alarm && <circle className="pulse" r="4.6" />}
            <circle className="ring" r="4.6" />
            <text textAnchor="middle" y="1.2" fontSize="3.3">
              {slot.status === "unmodelled" ? "GK" : slot.player ? initials(slot.player.name) : alarm ? "!" : "—"}
            </text>
            <text className="name" textAnchor="middle" y="8.6" fontSize="2.6">
              {slot.player ? lastName(slot.player.name) : slot.status === "unmodelled" ? "Not modelled" : slot.position}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
