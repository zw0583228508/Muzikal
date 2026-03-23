import { describe, it, expect } from "vitest";
import { cn, formatTime } from "@/lib/utils";

describe("cn (className merger)", () => {
  it("returns a single class unchanged", () => {
    expect(cn("text-white")).toBe("text-white");
  });

  it("merges multiple classes", () => {
    expect(cn("p-4", "text-sm")).toBe("p-4 text-sm");
  });

  it("resolves Tailwind conflicts — last wins", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("ignores falsy values", () => {
    expect(cn("flex", false, undefined, null as unknown as string, "gap-2")).toBe("flex gap-2");
  });

  it("handles conditional classes via object syntax", () => {
    expect(cn({ "opacity-0": false, "opacity-100": true })).toBe("opacity-100");
  });

  it("returns empty string when no valid classes", () => {
    expect(cn(false as unknown as string, undefined)).toBe("");
  });
});

describe("formatTime", () => {
  it("formats zero seconds as 00:00.00", () => {
    expect(formatTime(0)).toBe("00:00.00");
  });

  it("formats 65.5 seconds correctly", () => {
    expect(formatTime(65.5)).toBe("01:05.50");
  });

  it("formats 3661.25 (over one hour)", () => {
    expect(formatTime(3661.25)).toBe("61:01.25");
  });

  it("returns 00:00.00 for NaN input", () => {
    expect(formatTime(NaN)).toBe("00:00.00");
  });

  it("returns 00:00.00 for undefined-like falsy", () => {
    expect(formatTime(0)).toBe("00:00.00");
  });

  it("pads single-digit minutes and seconds", () => {
    expect(formatTime(9.5)).toBe("00:09.50");
  });

  it("handles millisecond precision", () => {
    const result = formatTime(1.999);
    expect(result).toBe("00:01.99");
  });
});
