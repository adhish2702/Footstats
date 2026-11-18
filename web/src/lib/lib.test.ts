import { describe, expect, it } from "vitest";
import type { PositionGap } from "../api/types";
import { path } from "../api/client";
import { fixed, gapVerdict, gaugeAngle, gaugeMax, initials, ordinal, signed } from "./format";
import { FORMATION, formationSlots } from "./formation";

describe("format", () => {
  it("makes initials from first and last names", () => {
    expect(initials("Martin Ødegaard")).toBe("MØ");
    expect(initials("Vitinha")).toBe("VI");
    expect(initials("Jan Paul van Hecke")).toBe("JH");
    expect(initials("  ")).toBe("?");
  });

  it("formats numbers with a true minus sign", () => {
    expect(fixed(0.4567)).toBe("0.46");
    expect(fixed(null)).toBe("—");
    expect(signed(0.2)).toBe("+0.20");
    expect(signed(-0.1)).toBe("−0.10");
    expect(signed(0.001)).toBe("0.00");
  });

  it("writes ordinals", () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 81, 100, 111].map(ordinal)).toEqual(
      ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "81st", "100th", "111th"],
    );
    expect(ordinal(null)).toBe("—");
  });

  it("calls a gap only when it beats the model's typical error", () => {
    expect(gapVerdict(0.2)).toBe("over");
    expect(gapVerdict(-0.3)).toBe("under");
    expect(gapVerdict(0.03)).toBe("level");
  });

  it("scales the gauge to the values shown", () => {
    expect(gaugeMax(0.3, 0.2)).toBe(0.8);
    expect(gaugeMax(1.3, 0.9)).toBe(1.4);
    expect(gaugeAngle(0, 1)).toBe(-90);
    expect(gaugeAngle(0.5, 1)).toBe(0);
    expect(gaugeAngle(2, 1)).toBe(90);
  });

  it("builds API paths without empty parameters", () => {
    expect(path("/players", { search: "kane", club: undefined, page: 2, league: "" })).toBe("/players?search=kane&page=2");
    expect(path("/clubs")).toBe("/clubs");
  });
});

describe("formation", () => {
  const gap = (position: PositionGap["position"], status: PositionGap["status"], names: string[]): PositionGap => ({
    position, status, squadPlayers: names.length, squadMinutes: 0, squadPredictedP90: null, squadActualP90: null,
    leaguePredictedP90: 0.1, differenceP90: null, vsLeaguePct: null,
    players: names.map((name, i) => ({ id: i + 1, name, minutes: 1000, predictedP90: 0.1, actualP90: 0.1 })),
  });

  it("is a 4-3-3 with a goalkeeper", () => {
    const count = (p: string) => FORMATION.filter((s) => s.position === p).length;
    expect([count("GKP"), count("DEF"), count("MID"), count("WNG"), count("STR")]).toEqual([1, 4, 3, 2, 1]);
  });

  it("fills slots with the club's players and their position's status", () => {
    const slots = formationSlots([
      gap("DEF", "weak", ["A", "B"]),
      gap("MID", "above", ["C", "D", "E", "F"]),
      gap("STR", "missing", []),
    ]);
    const defs = slots.filter((s) => s.position === "DEF");
    expect(defs.map((s) => s.player?.name ?? null)).toEqual(["A", "B", null, null]);
    expect(defs.every((s) => s.status === "weak")).toBe(true);
    expect(slots.filter((s) => s.position === "MID").map((s) => s.player?.name)).toEqual(["C", "D", "E"]);
    expect(slots.find((s) => s.position === "STR")).toMatchObject({ status: "missing", player: null });
    expect(slots.find((s) => s.position === "WNG")?.status).toBe("missing");
    expect(slots.find((s) => s.position === "GKP")?.status).toBe("unmodelled");
  });
});
