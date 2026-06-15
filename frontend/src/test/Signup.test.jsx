import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from "../contexts/AuthContext.jsx";
import Signup from "../pages/Signup.jsx";

const mockAuth = {
  signUp: vi.fn(),
  signInWithGoogle: vi.fn(),
  signInWithApple: vi.fn(),
};

describe("Signup page", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue(mockAuth);
  });

  it("renders the sign-up heading", () => {
    render(
      <MemoryRouter>
        <Signup />
      </MemoryRouter>
    );
    expect(screen.getByText("SIGN UP")).toBeInTheDocument();
  });

  it("renders the hero headline", () => {
    render(
      <MemoryRouter>
        <Signup />
      </MemoryRouter>
    );
    expect(screen.getByText("START YOUR TRADING JOURNEY.")).toBeInTheDocument();
  });
});
