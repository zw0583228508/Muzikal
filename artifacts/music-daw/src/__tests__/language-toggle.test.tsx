import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LanguageToggle } from "@/components/language-toggle";

const mockChangeLanguage = vi.fn();

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: "he",
      changeLanguage: mockChangeLanguage,
    },
  }),
}));

describe("LanguageToggle", () => {
  beforeEach(() => {
    mockChangeLanguage.mockClear();
  });

  it("renders the toggle button", () => {
    render(<LanguageToggle />);
    const button = screen.getByRole("button");
    expect(button).toBeInTheDocument();
  });

  it("shows EN when current language is Hebrew", () => {
    render(<LanguageToggle />);
    expect(screen.getByRole("button")).toHaveTextContent("EN");
  });

  it("calls changeLanguage with 'en' when Hebrew is active and button is clicked", () => {
    render(<LanguageToggle />);
    fireEvent.click(screen.getByRole("button"));
    expect(mockChangeLanguage).toHaveBeenCalledWith("en");
  });

  it("renders exactly one button element", () => {
    render(<LanguageToggle />);
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });
});
