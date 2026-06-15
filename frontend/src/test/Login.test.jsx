import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from "../contexts/AuthContext.jsx";
import Login from "../pages/Login.jsx";

const mockAuth = {
  user: null,
  signIn: vi.fn(),
  signInWithGoogle: vi.fn(),
  signInWithApple: vi.fn(),
  mfaChallenge: null,
  verifyMfa: vi.fn(),
  cancelMfa: vi.fn(),
};

describe("Login page", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue(mockAuth);
  });

  it("renders the sign-in heading", () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );
    expect(screen.getAllByText("SIGN IN").length).toBeGreaterThan(0);
  });

  it("renders the hero headline", () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );
    expect(screen.getByText("ADVANCED MARKET STRATEGY TERMINAL.")).toBeInTheDocument();
  });
});
