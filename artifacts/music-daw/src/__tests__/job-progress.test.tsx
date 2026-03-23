import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { JobProgress } from "@/components/job-progress";
import type { Job } from "@workspace/api-client-react";

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    jobId: "test-job-1",
    projectId: 1,
    type: "analysis",
    status: "running",
    progress: 50,
    currentStep: "Analyzing rhythm and tempo",
    isMock: false,
    errorMessage: null,
    errorCode: null,
    startedAt: new Date().toISOString() as unknown as Date,
    finishedAt: null,
    createdAt: new Date().toISOString() as unknown as Date,
    updatedAt: new Date().toISOString() as unknown as Date,
    inputPayload: null,
    ...overrides,
  } as unknown as Job;
}

describe("JobProgress component", () => {
  it("renders nothing when job is null", () => {
    const { container } = render(<JobProgress job={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when job is undefined", () => {
    const { container } = render(<JobProgress job={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows progress percentage when running", () => {
    render(<JobProgress job={makeJob({ progress: 73 })} />);
    expect(screen.getByText("73%")).toBeInTheDocument();
  });

  it("shows MOCK badge when isMock=true", () => {
    render(<JobProgress job={makeJob({ isMock: true })} />);
    expect(screen.getByText("MOCK")).toBeInTheDocument();
  });

  it("does not show MOCK badge when isMock=false", () => {
    render(<JobProgress job={makeJob({ isMock: false })} />);
    expect(screen.queryByText("MOCK")).not.toBeInTheDocument();
  });

  it("displays the current step text", () => {
    render(<JobProgress job={makeJob({ currentStep: "Detecting key and mode" })} />);
    expect(screen.getByText("Detecting key and mode")).toBeInTheDocument();
  });

  it("renders for completed job status", () => {
    render(<JobProgress job={makeJob({ status: "completed", progress: 100 })} />);
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("renders for failed job status", () => {
    render(<JobProgress job={makeJob({ status: "failed", progress: 0, currentStep: "Python backend unavailable" })} />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });

  it("shows correct job type label", () => {
    render(<JobProgress job={makeJob({ type: "arrangement" })} />);
    expect(screen.getByText(/arrangement/i)).toBeInTheDocument();
  });
});
