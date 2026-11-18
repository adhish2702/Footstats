// Shapes returned by the FootStats API (api/src). Keep in step with the API.

export type Position = "GKP" | "DEF" | "MID" | "WNG" | "STR";
export type League = "Premier League" | "La Liga" | "Serie A" | "Bundesliga" | "Ligue 1";

export interface ClubRef {
  id: number;
  name: string;
  league: League;
}

export interface Prediction {
  predictedP90: number;
  actualP90: number;
  gapP90: number;
}

export interface PlayerSummary {
  id: number;
  name: string;
  club: ClubRef;
  position: Position;
  role: string;
  age: number | null;
  minutes: number;
  qualified: boolean;
  rating: number;
  npgaP90: number;
  prediction: Prediction | null;
}

export interface PlayerPage {
  data: PlayerSummary[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  sort: string;
}

export interface StyleFeature {
  key: string;
  label: string;
  value: number;
  percentile: number | null;
  lowerIsBetter: boolean;
}

export interface PlayerDetail extends PlayerSummary {
  clubsPlayed: string;
  nationality: string | null;
  birthYear: number | null;
  appearances: number;
  starts: number;
  prediction: (Prediction & { modelVersion: string; inTestSet: boolean }) | null;
  stats: {
    output: {
      goals: number; assists: number; penaltyGoals: number; nonPenaltyGoals: number;
      xg: number; npxg: number; xag: number; npgaP90: number; npxgP90: number; xagP90: number;
    };
    defending: { tacklesWonP90: number; interceptionsP90: number; clearancesP90: number; passAccuracyPct: number };
    goalkeeping: { savesPct: number; cleanSheets: number; goalsConceded: number; goalsPrevented: number } | null;
  };
  style: { comparedWith: string; features: StyleFeature[] };
}

export interface Club extends ClubRef {
  players: number;
  playersWithPrediction: number;
}

export type GapStatus = "missing" | "weak" | "below" | "above";

export interface PositionGap {
  position: Exclude<Position, "GKP">;
  status: GapStatus;
  squadPlayers: number;
  squadMinutes: number;
  squadPredictedP90: number | null;
  squadActualP90: number | null;
  leaguePredictedP90: number;
  differenceP90: number | null;
  vsLeaguePct: number | null;
  players: { id: number; name: string; minutes: number; predictedP90: number; actualP90: number }[];
}

export interface ClubGaps {
  club: ClubRef;
  method: string;
  weakest: Position | null;
  positions: PositionGap[];
}

export interface OverUnder {
  model: { version: string; testMae: number } | null;
  note: string;
  overperformers: PlayerSummary[];
  underperformers: PlayerSummary[];
}

export interface ModelInfo {
  version: string;
  modelName: string;
  target: string;
  season: string;
  players: number;
  trainPlayers: number;
  testPlayers: number;
  metrics: {
    testMae: number; baselineMae: number; errorReductionPct: number; testR2: number;
    cvMae: number; xgMae: number; xgR2: number;
  };
  featureImportance: { feature: string; importance: number }[];
}

export interface ApiErrorBody {
  error: { status: number; message: string; details?: { param: string; message: string }[] };
}
