import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Terms from "../pages/Terms.jsx";

describe("Terms page", () => {
  it("renders the Terms of Service heading", () => {
    render(
      <MemoryRouter>
        <Terms />
      </MemoryRouter>
    );
    expect(screen.getByText("Terms of Service")).toBeInTheDocument();
  });

  it("displays the effective date", () => {
    render(
      <MemoryRouter>
        <Terms />
      </MemoryRouter>
    );
    expect(screen.getByText(/Effective.*March 5, 2026/)).toBeInTheDocument();
  });

  it("contains the acceptance section", () => {
    render(
      <MemoryRouter>
        <Terms />
      </MemoryRouter>
    );
    expect(screen.getByText("1. Acceptance")).toBeInTheDocument();
  });
});
