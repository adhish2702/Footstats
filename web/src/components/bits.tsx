// Small presentational pieces used across pages.
import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";
import type { ClubRef, GapStatus, KeeperVsXg, Position, Prediction } from "../api/types";
import { useCountUp } from "../hooks/motion";
import { POSITION_NAMES, STATUS_TEXT, gapVerdict, initials, keeperVerdict, signed } from "../lib/format";
import { AlertIcon, DownIcon, LevelIcon, UpIcon } from "./icons";

/** Glass panel with cut corners. `as="link"` makes the whole panel a link. */
export function Panel({ children, className = "", style, index, to, label }: {
  children: ReactNode; className?: string; style?: CSSProperties; index?: number; to?: string; label?: string;
}) {
  const cls = `panel ${index !== undefined ? "enter" : ""} ${to ? "panel--link" : ""} ${className}`;
  const s = { ...style, ...(index !== undefined && { "--i": Math.min(index, 12) }) } as CSSProperties;
  if (to) {
    return <Link to={to} className={cls} style={s} aria-label={label}>{children}</Link>;
  }
  return <section className={cls} style={s} aria-label={label}>{children}</section>;
}

/** Initials in a circle. Player photos are trademarked, so there are none. */
export function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  return (
    <span className="avatar" style={{ "--size": `${size}px` } as CSSProperties} aria-hidden="true">
      {initials(name)}
    </span>
  );
}

/** Club name as a neutral text badge (no crests or club colours). */
export function ClubBadge({ club, link = true }: { club: Pick<ClubRef, "id" | "name">; link?: boolean }) {
  return link
    ? <Link className="club-badge" to={`/clubs/${club.id}`} title={`${club.name}: squad gaps`}>{club.name}</Link>
    : <span className="club-badge">{club.name}</span>;
}

export function PositionChip({ position }: { position: Position }) {
  return <abbr className="pos-chip" title={POSITION_NAMES[position]}>{position}</abbr>;
}

/** A number that counts up from zero when it first appears. */
export function CountUp({ value, digits = 2, signedValue = false }: { value: number; digits?: number; signedValue?: boolean }) {
  const shown = useCountUp(value);
  return (
    <span className="num" aria-label={signedValue ? signed(value, digits) : value.toFixed(digits)}>
      <span aria-hidden="true">{signedValue ? signed(shown, digits) : shown.toFixed(digits)}</span>
    </span>
  );
}

/**
 * Actual minus predicted, with an icon and a word so it never relies on colour:
 * ▲ over, ▼ under, or level when the gap is within the model's typical error.
 */
export function GapVerdict({ prediction, typicalError, compact = false }: {
  prediction: Prediction | null; typicalError?: number; compact?: boolean;
}) {
  if (!prediction) {
    return <span className="verdict verdict--none" title="The model covers outfield players with 900+ minutes">Not modelled</span>;
  }
  const verdict = gapVerdict(prediction.gapP90, typicalError);
  const Icon = verdict === "over" ? UpIcon : verdict === "under" ? DownIcon : LevelIcon;
  const word = verdict === "over" ? "Over" : verdict === "under" ? "Under" : "Level";
  return (
    <span className={`verdict verdict--${verdict}`}>
      <Icon size={compact ? 11 : 13} />
      <span className="num">{signed(prediction.gapP90)}</span>
      <span className={compact ? "sr-only" : ""}>{word}</span>
    </span>
  );
}

/**
 * The "vs expected" verdict for any player: the model's gap for outfield
 * players, goals prevented against post-shot xG for goalkeepers.
 */
export function VsExpected({ player, typicalError, compact = false }: {
  player: { prediction: Prediction | null; keeper: KeeperVsXg | null }; typicalError?: number; compact?: boolean;
}) {
  if (player.prediction || !player.keeper) {
    return <GapVerdict prediction={player.prediction} typicalError={typicalError} compact={compact} />;
  }
  const verdict = keeperVerdict(player.keeper.preventedP90);
  const Icon = verdict === "over" ? UpIcon : verdict === "under" ? DownIcon : LevelIcon;
  const word = verdict === "over" ? "Prevented" : verdict === "under" ? "Conceded extra" : "Level";
  return (
    <span className={`verdict verdict--${verdict}`}
      title="Goalkeeper: goals prevented per 90, post-shot xG faced minus goals conceded">
      <Icon size={compact ? 11 : 13} />
      <span className="num">{signed(player.keeper.preventedP90)}</span>
      <span className={compact ? "sr-only" : ""}>{word}</span>
      <span className="verdict__tag">GK</span>
    </span>
  );
}

export function StatusTag({ status }: { status: GapStatus | "unmodelled" }) {
  const Icon = status === "above" ? UpIcon : status === "below" ? DownIcon : status === "unmodelled" ? LevelIcon : AlertIcon;
  const text = status === "unmodelled" ? "Not modelled" : STATUS_TEXT[status];
  return <span className={`status-tag status-tag--${status}`}><Icon size={13} />{text}</span>;
}
