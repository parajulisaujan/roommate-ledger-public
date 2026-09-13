import { describe, it, expect } from "vitest";
import { cents, dollars, equalPreview } from "./money";
describe("exact decimal input", () => {
  it("parses cents without floating point multiplication", () => {
    expect(cents("12.99")).toBe(1299);
    expect(cents("0.29")).toBe(29);
    expect(cents("4.1")).toBe(410);
  });
  it("rejects hidden rounding, exponents and negatives", () => {
    for (const value of ["1.999", "1e3", "-1", "NaN", "Infinity", ""])
      expect(() => cents(value)).toThrow();
  });
  it("round trips cents", () => {
    for (let i = 0; i < 10000; i += 13) expect(cents(dollars(i))).toBe(i);
  });
  it("shows cent remainders honestly", () => {
    expect(equalPreview(10000, 3)).toBe("$33.33–$33.34 each");
    expect(equalPreview(10000, 4)).toBe("$25.00 each");
  });
});
