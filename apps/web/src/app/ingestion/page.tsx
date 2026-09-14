"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { PageHeader, Card, SectionHeader, StatusBadge } from "@/components/ui";

export default function IngestionPage() {
  const { can, roles } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string>("");

  if (!can("create:vessel_call")) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <StatusBadge label="Access Denied — missing create:vessel_call permission" tone="critical" />
      </div>
    );
  }

  const handleUpload = async () => {
    if (!file) return;
    setStatus("Uploading...");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/v1/ingestion/upload", {
        method: "POST",
        body: formData,
        // credentials: "omit", // in real, we pass token
      });

      if (!res.ok) throw new Error("Upload failed");

      const data = await res.json();
      setStatus(`Success! Batch ID: ${data.batch_id}`);
    } catch (error) {
      const e = error as Error;
      setStatus(`Error: ${e.message}`);
    }
  };

  const loadSynthetic = async () => {
    setStatus("Loading synthetic dataset...");
    try {
      const res = await fetch("/api/v1/ingestion/synthetic", { method: "POST" });
      if (!res.ok) throw new Error("Synthetic load failed");
      const data = await res.json();
      setStatus(`Synthetic data loaded. Batch ID: ${data.batch_id}`);
    } catch (error) {
      const e = error as Error;
      setStatus(`Error: ${e.message}`);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[var(--color-bg)] overflow-y-auto">
      <PageHeader
        title="Data Ingestion"
        description="Upload source data files or load the governed synthetic benchmark dataset through the standard ingestion pipeline."
      />

      <div className="p-6 max-w-3xl w-full mx-auto space-y-6">
        <Card>
          <SectionHeader title="Upload Data File" description="Accepted formats follow the standard ingestion contract." />
          <div className="space-y-4">
            <input
              type="file"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="block w-full text-sm text-[var(--color-text-secondary)] border border-[var(--color-border)] rounded-md p-2 file:mr-3 file:px-3 file:py-1.5 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-[var(--color-accent-soft)] file:text-[var(--color-accent)] cursor-pointer"
            />
            <button
              onClick={handleUpload}
              disabled={!file}
              className="px-4 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              Upload &amp; Process
            </button>
          </div>
        </Card>

        {(roles.includes("Platform Administrator") || roles.includes("Developer")) && (
          <Card className="border-[var(--color-warning-border)] bg-[var(--color-warning-bg)]">
            <SectionHeader
              title="Synthetic Test Dataset"
              description="Resets the synthetic tenant and loads the fixture data through the standard ingestion pipeline."
            />
            <button
              onClick={loadSynthetic}
              className="px-4 py-1.5 bg-[var(--color-warning)] hover:opacity-90 text-white rounded-md text-sm font-medium cursor-pointer"
            >
              Load Synthetic Dataset
            </button>
          </Card>
        )}

        {status && (
          <Card className="text-sm text-[var(--color-text-secondary)]">
            <span className="font-medium text-[var(--color-text-primary)]">Status: </span>
            {status}
          </Card>
        )}
      </div>
    </div>
  );
}
