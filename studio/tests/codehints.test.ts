import { describe, expect, it } from "vitest";
import { hintsAt } from "../src/ui/codehints";

const names = (before: string, source = before) => hintsAt(before, source).list.map((x) => x.name);

describe("hints while writing a room", () => {
  it("finishes Purple's names, the room's own, and grid's", () => {
    expect(names("    sa")).toEqual(["say"]);
    expect(names("grid.ra")).toEqual(["grid.random_empty"]);
    expect(names("    sc", "score = 0\n    sc")).toContain("score");
  });

  it("finds a call by what it does", () => {
    expect(names("speak")).toContain("say");
    expect(names("wait")).toContain("after");
  });

  it("goes in with its quotes when a call takes words", () => {
    expect(hintsAt("    sa", "").list[0].insert).toBe('say("")');
    expect(hintsAt("    drum", "").list).toEqual([]);
    expect(hintsAt("    dr", "").list[0].insert).toBe('drum("")');
    expect(hintsAt("    grid.ra", "").list[0].insert).toBe("grid.random_empty()");
  });

  it("stays quiet in strings, comments, and once a name is whole", () => {
    expect(names('say("sa')).toEqual([]);
    expect(names("# sa")).toEqual([]);
    expect(names("say")).toEqual([]);
  });

  it("shows what an open call takes, even partway through its words", () => {
    expect(hintsAt('    say("hel', "").call?.call).toBe('say("Hello!")');
    expect(hintsAt("    play(", "").call?.about).toMatch(/note/i);
    expect(hintsAt("    say(x) ", "").call).toBeUndefined();
  });
});
