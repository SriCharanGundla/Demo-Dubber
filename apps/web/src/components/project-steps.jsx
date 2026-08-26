import { Link } from "react-router-dom";
import { Check, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

const steps = [
  { id: "transcribe", label: "Transcribe" },
  { id: "transcript", label: "Edit transcript" },
  { id: "export", label: "Export" },
];

export function ProjectSteps({ project, active }) {
  const hasTranscript = Boolean(project.transcript_cues?.length);
  const activeIndex = steps.findIndex((step) => step.id === active);

  return (
    <nav aria-label="Project progress" className="mb-6 overflow-x-auto">
      <ol className="flex min-w-max items-center gap-2">
        <li>
          <Link
            className="text-sm font-semibold text-muted-foreground hover:text-foreground"
            to="/projects"
          >
            Projects
          </Link>
        </li>
        <ChevronRight size={15} className="text-muted-foreground" />
        {steps.map((step, index) => {
          const enabled = step.id === "transcribe" || hasTranscript;
          const complete = index < activeIndex || (hasTranscript && index === 0);
          const content = (
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-semibold",
                step.id === active
                  ? "border-primary bg-primary text-primary-foreground"
                  : enabled
                    ? "border-border bg-card hover:bg-muted"
                    : "border-border bg-muted text-muted-foreground opacity-55",
              )}
            >
              {complete && <Check size={14} />}
              {index + 1}. {step.label}
            </span>
          );
          return (
            <li key={step.id} className="flex items-center gap-2">
              {enabled ? (
                <Link to={`/projects/${project.project_id}/${step.id}`}>
                  {content}
                </Link>
              ) : (
                content
              )}
              {index < steps.length - 1 && (
                <ChevronRight size={15} className="text-muted-foreground" />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
