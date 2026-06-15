import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";

vi.mock("../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from "../contexts/AuthContext.jsx";
import { useAuthHeaders, useAuthQueryParam } from "../hooks/useAuthHeaders.js";

describe("useAuthHeaders", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({ session: null });
  });

  it("does not send Bearer when not logged in", () => {
    const { result } = renderHook(() => useAuthHeaders());
    const headers = result.current();
    expect(headers.Authorization).toBeUndefined();
  });

  it("returns Bearer header when session has access_token", () => {
    vi.mocked(useAuth).mockReturnValue({
      session: { access_token: "jwt-token-abc" },
    });
    const { result } = renderHook(() => useAuthHeaders());
    expect(result.current()).toEqual({ Authorization: "Bearer jwt-token-abc" });
  });
});

describe("useAuthQueryParam", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({ session: null });
  });

  it("does not send token query when not logged in", () => {
    const { result } = renderHook(() => useAuthQueryParam());
    const param = result.current();
    expect(param.startsWith("?token=")).toBe(false);
  });

  it("returns token query param when session exists", () => {
    vi.mocked(useAuth).mockReturnValue({
      session: { access_token: "jwt-token-xyz" },
    });
    const { result } = renderHook(() => useAuthQueryParam());
    expect(result.current()).toBe("?token=jwt-token-xyz");
  });
});
