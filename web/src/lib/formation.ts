import type { GapStatus, KeeperGap, Position, PositionGap } from "../api/types";

/** A 4-3-3 on a vertical pitch, 0-100 in both directions, attacking upwards. */
export const FORMATION: { position: Position; x: number; y: number }[] = [
  { position: "GKP", x: 50, y: 92 },
  { position: "DEF", x: 15, y: 74 },
  { position: "DEF", x: 38, y: 78 },
  { position: "DEF", x: 62, y: 78 },
  { position: "DEF", x: 85, y: 74 },
  { position: "MID", x: 24, y: 50 },
  { position: "MID", x: 50, y: 57 },
  { position: "MID", x: 76, y: 50 },
  { position: "WNG", x: 16, y: 26 },
  { position: "WNG", x: 84, y: 26 },
  { position: "STR", x: 50, y: 18 },
];

export interface FormationSlot {
  position: Position;
  x: number;
  y: number;
  status: GapStatus | "unmodelled";
  /** The player filling this slot: the club's regulars at the position, by minutes. */
  player: { id: number; name: string } | null;
}

/**
 * Place a club's qualified players into the 4-3-3 slots and colour them by their
 * position's status. The goalkeeper slot uses goals prevented when it's given.
 */
export function formationSlots(positions: PositionGap[], goalkeeper?: KeeperGap): FormationSlot[] {
  const used = new Map<Position, number>();
  return FORMATION.map((slot) => {
    if (slot.position === "GKP") {
      if (!goalkeeper) return { ...slot, status: "unmodelled", player: null };
      const keeper = goalkeeper.players[0];
      return { ...slot, status: goalkeeper.status, player: keeper ? { id: keeper.id, name: keeper.name } : null };
    }
    const gap = positions.find((p) => p.position === slot.position);
    const index = used.get(slot.position) ?? 0;
    used.set(slot.position, index + 1);
    const player = gap?.players[index];
    return {
      ...slot,
      status: gap?.status ?? "missing",
      player: player ? { id: player.id, name: player.name } : null,
    };
  });
}
