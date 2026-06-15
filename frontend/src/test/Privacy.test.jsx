import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Privacy from "../pages/Privacy.jsx";

describe("Privacy page", () => {
  it("renders the Privacy Policy heading", () => {
    render(
      <MemoryRouter>
        <Privacy />
      </MemoryRouter>
    );
    expect(screen.getByText("PRIVACY POLICY")).toBeInTheDocument();
  });

  it("displays the effective date", () => {
    render(
      <MemoryRouter>
        <Privacy />
      </MemoryRouter>
    );
    expect(screen.getByText(/Effective.*March 5, 2026/)).toBeInTheDocument();
  });

  it("mentions data collection", () => {
    render(
      <MemoryRouter>
        <Privacy />
      </MemoryRouter>
    );
    expect(screen.getByText("1. What We Collect")).toBeInTheDocument();
  });
});
