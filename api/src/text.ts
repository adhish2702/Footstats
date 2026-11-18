/**
 * Name folding for search. Must match search_key() in pipeline/load_db.py,
 * which fills players.search_name: lower case, accents removed, so
 * "odegaard" finds "Martin Ødegaard".
 */

// Letters Unicode does not split into a base letter plus an accent.
const SPECIAL_LETTERS: Record<string, string> = {
  ø: "o", Ø: "O", đ: "d", Đ: "D", ł: "l", Ł: "L", ß: "ss", æ: "ae", Æ: "AE",
  ı: "i", ð: "d", Ð: "D", þ: "th", Þ: "Th", "’": "'",
};
const SPECIAL_PATTERN = new RegExp(`[${Object.keys(SPECIAL_LETTERS).join("")}]`, "g");

export function foldName(name: string): string {
  return name
    .replace(SPECIAL_PATTERN, (ch) => SPECIAL_LETTERS[ch] ?? ch)
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/** Escape LIKE wildcards so a search for "%" or "_" matches those characters literally. */
export function escapeLike(text: string): string {
  return text.replace(/[\\%_]/g, (ch) => `\\${ch}`);
}
