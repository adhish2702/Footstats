import { escapeLike, foldName } from "../src/text";

// The same pairs as SEARCH_KEYS in pipeline/tests/test_load_db.py: the pipeline
// stores names folded this way, and the API folds search text to match.
const SEARCH_KEYS: Record<string, string> = {
  "Martin Ødegaard": "martin odegaard",
  "Đorđe Petrović": "dorde petrovic",
  "Kylian Mbappé": "kylian mbappe",
  "Son Heung-min": "son heung-min",
  "  Obite  N'Dicka ": "obite n'dicka",
  "Hakan Çalhanoğlu": "hakan calhanoglu",
  "Þórir Jóhann Helgason": "thorir johann helgason",
  "Albert Guðmundsson": "albert gudmundsson",
  "Nico O’Reilly": "nico o'reilly",
};

describe("foldName", () => {
  it.each(Object.entries(SEARCH_KEYS))("%s -> %s", (name, key) => {
    expect(foldName(name)).toBe(key);
  });
});

describe("escapeLike", () => {
  it("escapes LIKE wildcards", () => {
    expect(escapeLike("50%_a\\b")).toBe("50\\%\\_a\\\\b");
  });
});
