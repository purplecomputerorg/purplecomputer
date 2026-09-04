import { describe, expect, it } from "vitest";
import golden from "./room-golden.json";
import { noise } from "../sdk/src/purple/synth";
import { RoomError, Runner, TraceHost, formatValue, parse, parseNote } from "../sdk/src/room";

// room-golden.json is written by scripts/export_studio.py: the sample program run by
// purple_tui/room_program.py with mulberry32 noise as its random source. Same seed here.
describe("room interpreter matches purple_tui.room_program", () => {
  it("produces the golden trace and variables", async () => {
    const unit = noise(golden.seed);
    const host = new TraceHost();
    const runner = new Runner(parse(golden.program), host, () => (unit() + 1) / 2);
    for (const [event, key] of golden.events as [string, string?][]) await runner.fire(event, key ?? "");
    expect(host.trace).toEqual(golden.trace);
    expect(runner.vars).toEqual(golden.vars);
  });

  it("formats and parses like the Python", () => {
    expect(formatValue(3)).toBe("3");
    expect(formatValue(2.5)).toBe("2.5");
    expect(formatValue(1 / 3)).toBe("0.3333");
    expect(parseNote("f#3")).toEqual(["F#", 3]);
    expect(parseNote("H2")).toBeNull();
  });

  it("refuses what Purple refuses", () => {
    expect(() => parse({ name: "Bad Name", rules: [] })).toThrow(RoomError);
    expect(() => parse({ name: "ok", rules: [{ when: { event: "jump" }, do: [] }] })).toThrow(/event must be/);
    expect(() => parse({ name: "ok", rules: [{ when: { event: "key", key: "a" }, do: [{ do: "play", note: "H9" }] }] })).toThrow(/note must look like/);
    expect(() => parse({ name: "ok", rules: [{ when: { event: "key", key: "a" }, do: [{ do: "show", text: { wat: 1 } }] }] })).toThrow(/unknown value block/);
  });
});
