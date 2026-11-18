import { z } from "zod";
import { HttpError } from "./errors";

export const LEAGUES = ["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1"] as const;
export const POSITIONS = ["GKP", "DEF", "MID", "WNG", "STR"] as const;
/** Positions the model covers (it predicts outfield output only). */
export const OUTFIELD = ["DEF", "MID", "WNG", "STR"] as const;
export const MAX_COMPARE = 3;

const MAX_ID = 2_147_483_647; // PostgreSQL integer

/** A positive whole number given as text, e.g. "42". */
export const id = z
  .string()
  .regex(/^\d+$/, "must be a positive whole number")
  .transform(Number)
  .refine((n) => n >= 1 && n <= MAX_ID, "must be a positive whole number");

function wholeNumber(min: number, max: number, fallback: number) {
  return z
    .string()
    .regex(/^\d+$/, "must be a whole number")
    .transform(Number)
    .refine((n) => n >= min && n <= max, `must be between ${min} and ${max}`)
    .optional()
    .transform((n) => n ?? fallback);
}

export const SORT_FIELDS = ["name", "age", "minutes", "rating", "npga", "predicted", "actual", "gap", "prevented"] as const;

export const playersQuery = z
  .object({
    search: z.string().trim().min(1).max(50).optional(),
    club: id.optional(),
    league: z.enum(LEAGUES).optional(),
    position: z.enum(POSITIONS).optional(),
    // A field name, optionally prefixed with "-" for descending: "rating", "-gap".
    sort: z
      .string()
      .regex(new RegExp(`^-?(${SORT_FIELDS.join("|")})$`), `must be one of ${SORT_FIELDS.join(", ")}, optionally prefixed with "-"`)
      .optional()
      .transform((s) => s ?? "-rating"),
    page: wholeNumber(1, 100_000, 1),
    pageSize: wholeNumber(1, 100, 20),
  })
  .strict();

export const clubsQuery = z.object({ league: z.enum(LEAGUES).optional() }).strict();

export const compareQuery = z
  .object({
    ids: z
      .string()
      .regex(/^\d+(,\d+)*$/, "must be a comma-separated list of player ids, e.g. 1,2,3")
      .transform((s) => s.split(",").map(Number))
      .refine((ids) => ids.length <= MAX_COMPARE, `at most ${MAX_COMPARE} players`)
      .refine((ids) => new Set(ids).size === ids.length, "must not repeat a player")
      .refine((ids) => ids.every((n) => n >= 1 && n <= MAX_ID), "ids must be positive whole numbers"),
  })
  .strict();

export const overUnderQuery = z
  .object({
    limit: wholeNumber(1, 50, 10),
    position: z.enum(OUTFIELD).optional(),
    league: z.enum(LEAGUES).optional(),
  })
  .strict();

export const emptyQuery = z.object({}).strict();

/** Parse request input or throw a 400 that names each bad parameter. */
export function parse<T extends z.ZodType>(schema: T, input: unknown, what = "query parameter"): z.output<T> {
  const result = schema.safeParse(input);
  if (result.success) return result.data;
  const details = result.error.issues.map((issue) => {
    if (issue.code === "unrecognized_keys") {
      return { param: issue.keys.join(", "), message: `unknown ${what}` };
    }
    return { param: issue.path.join(".") || "(input)", message: issue.message };
  });
  throw new HttpError(400, `Invalid ${what}s`, details);
}
