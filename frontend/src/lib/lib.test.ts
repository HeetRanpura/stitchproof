import { describe, expect, it } from "vitest";
import { createSseParser } from "./sse";
import { niceTicks, silhouetteBars } from "./chart";
import { countChip, isFlagged, STATUS } from "./status";
import type { LineResult } from "../types";

function line(p: Partial<LineResult>): LineResult {
  return {
    index: 0, text: "", label: null, kind: "round", status: "OK", available: null, used: null,
    made: null, stated: null, codes: [], explanation: "", program_text: "", rows_made: [], ...p,
  };
}

describe("sse parser", () => {
  it("parses events split across chunks", () => {
    const feed = createSseParser();
    expect(feed('event: start\ndata: {"lines":["a"]}\n\nevent: li')).toEqual([{ event: "start", data: { lines: ["a"] } }]);
    expect(feed('ne\ndata: {"index":0}\n\n')).toEqual([{ event: "line", data: { index: 0 } }]);
    expect(feed("")).toEqual([]);
  });
  it("handles CRLF", () => {
    const feed = createSseParser();
    expect(feed('event: done\r\ndata: {"ok":true}\r\n\r\n')).toEqual([{ event: "done", data: { ok: true } }]);
  });
});

describe("silhouette bars", () => {
  it("expands ranges, skips notes and foundation chains", () => {
    const bars = silhouetteBars([
      line({ index: 0, kind: "note", status: "NOTE" }),
      line({ index: 1, kind: "foundation", made: 21 }),
      line({ index: 2, label: "Rnd 1", made: 6, rows_made: [6], stated: 6 }),
      line({ index: 3, label: "Rnds 2-3", made: 12, rows_made: [12, 12], stated: 12 }),
      undefined,
      line({ index: 5, label: "Rnd 4", status: "ERROR", made: 15, rows_made: [15], stated: 18 }),
    ]);
    expect(bars.map((b) => b.label)).toEqual(["Rnd 1", "Rnds 2-3 (1)", "Rnds 2-3 (2)", "Rnd 4"]);
    expect(bars[3]).toMatchObject({ status: "ERROR", made: 15, stated: 18, lineIndex: 5 });
  });
  it("falls back to the stated count for rows that couldn't be checked", () => {
    const bars = silhouetteBars([line({ index: 0, label: "Rnd 7", status: "CAN'T CHECK", stated: 36 })]);
    expect(bars[0].made).toBe(36);
  });
});

describe("ticks", () => {
  it("covers the max with round steps", () => {
    expect(niceTicks(36)).toEqual([0, 10, 20, 30, 40]);
    expect(niceTicks(6)).toEqual([0, 2, 4, 6]);
    expect(niceTicks(0)).toEqual([0]);
  });
});

describe("status", () => {
  it("never relies on colour alone: every status has a word", () => {
    for (const s of Object.values(STATUS)) expect(s.word.length).toBeGreaterThan(1);
    expect(isFlagged("ERROR")).toBe(true);
    expect(isFlagged("OK")).toBe(false);
  });
  it("count chip", () => {
    expect(countChip(30, 31)).toBe("makes 30 · says 31");
    expect(countChip(24, 24)).toBe("24");
    expect(countChip(12, null)).toBe("makes 12");
    expect(countChip(null, null)).toBeNull();
  });
});
