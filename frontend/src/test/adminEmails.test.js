import { describe, it, expect, vi } from "vitest";

describe("isAdminEmail", () => {
  it("returns false for non-admin emails", async () => {
    const { isAdminEmail } = await import("../utils/adminEmails.js");
    expect(isAdminEmail("random@gmail.com")).toBe(false);
    expect(isAdminEmail("hacker@evil.com")).toBe(false);
  });

  it("returns false for falsy values", async () => {
    const { isAdminEmail } = await import("../utils/adminEmails.js");
    expect(isAdminEmail(null)).toBe(false);
    expect(isAdminEmail(undefined)).toBe(false);
    expect(isAdminEmail("")).toBe(false);
  });

  it("is case-insensitive (matching should be lowered)", async () => {
    const { isAdminEmail } = await import("../utils/adminEmails.js");
    // Whatever the admin email is, uppercase should match too
    const lowerResult = isAdminEmail("feichangfuyou@doyou.trade");
    const upperResult = isAdminEmail("FEICHANGFUYOU@DOYOU.TRADE");
    expect(lowerResult).toBe(upperResult);
  });

  it("isAdminEmail is a function", async () => {
    const { isAdminEmail } = await import("../utils/adminEmails.js");
    expect(typeof isAdminEmail).toBe("function");
  });
});
