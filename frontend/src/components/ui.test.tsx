import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge, ScoreBar } from "./ui";

describe("Badge — status is text, not colour alone", () => {
  it("renders an icon and a readable label", () => {
    render(<Badge status="suspected_infinite_loop" label="suspected infinite loop" />);
    expect(screen.getByText(/suspected infinite loop/)).toBeInTheDocument();
  });
  it("humanizes underscored statuses", () => {
    render(<Badge status="needs_review" />);
    expect(screen.getByText("needs review")).toBeInTheDocument();
  });
});

describe("ScoreBar", () => {
  it("exposes a progressbar role with the value", () => {
    render(<ScoreBar value={85.2} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "85.2");
  });
});
