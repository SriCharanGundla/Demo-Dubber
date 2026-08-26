import { CircleAlert, CircleCheck, LoaderCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

export function JobProgress({ job }) {
  if (!job) return null;
  const progress = job.total
    ? Math.round(((job.completed || 0) / job.total) * 100)
    : job.status === "succeeded"
      ? 100
      : 5;
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 font-semibold">
          {["queued", "running"].includes(job.status) && (
            <LoaderCircle className="animate-spin" size={17} />
          )}
          {job.status === "failed" && <CircleAlert size={17} />}
          {job.status === "succeeded" && <CircleCheck size={17} />}
          {job.message}
        </span>
        <Badge
          variant={
            job.status === "succeeded"
              ? "success"
              : job.status === "failed"
                ? "destructive"
                : "info"
          }
        >
          {job.status}
        </Badge>
      </div>
      <Progress
        value={progress}
        variant={job.status === "failed" ? "destructive" : "default"}
      />
      {job.status === "failed" && (
        <div className="mt-3 rounded-lg border border-destructive/20 bg-destructive/5 p-3">
          <p className="text-sm font-semibold text-destructive">
            Failed during: {job.failed_at || "Unknown processing step"}
          </p>
          {job.error && (
            <p className="mt-1 break-words text-sm text-destructive/90">
              {job.error}
            </p>
          )}
        </div>
      )}
      {job.total && (
        <p className="mt-2 text-right text-xs text-muted-foreground">
          {progress}%
        </p>
      )}
    </Card>
  );
}
