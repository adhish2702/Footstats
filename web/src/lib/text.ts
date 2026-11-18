/** Lower case without accents, for matching typed text against names ("odegaard" ~ "Ødegaard"). */
const SPECIAL: Record<string, string> = {
  ø: "o", Ø: "O", đ: "d", Đ: "D", ł: "l", Ł: "L", ß: "ss", æ: "ae", Æ: "AE",
  ı: "i", ð: "d", Ð: "D", þ: "th", Þ: "Th", "’": "'",
};
const PATTERN = new RegExp(`[${Object.keys(SPECIAL).join("")}]`, "g");

export function foldName(text: string): string {
  return text
    .replace(PATTERN, (ch) => SPECIAL[ch] ?? ch)
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}
