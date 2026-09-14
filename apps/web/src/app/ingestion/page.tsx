"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";

export default function IngestionPage() {
  const { principal } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string>("");

  if (!principal?.permissions.includes("create:vessel_call")) {
    return <div className="p-8 text-red-500">Access Denied: Missing create:vessel_call permission</div>;
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
    } catch (e: any) {
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
    } catch (e: any) {
      setStatus(`Error: ${e.message}`);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold">Data Ingestion</h1>
      
      <div className="border p-6 rounded-lg space-y-4">
        <h2 className="text-xl font-semibold">Upload Data File</h2>
        <input 
          type="file" 
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="block w-full border p-2"
        />
        <button 
          onClick={handleUpload}
          disabled={!file}
          className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          Upload & Process
        </button>
      </div>

      {principal.roles.includes("Platform Administrator") || principal.roles.includes("Developer") ? (
        <div className="border p-6 rounded-lg space-y-4 bg-orange-50 border-orange-200">
          <h2 className="text-xl font-semibold text-orange-800">Synthetic Test Dataset</h2>
          <p className="text-sm text-orange-700">
            This action will reset the synthetic tenant and load the fixture data through the standard ingestion pipeline.
          </p>
          <button 
            onClick={loadSynthetic}
            className="bg-orange-600 text-white px-4 py-2 rounded"
          >
            Load Synthetic Dataset
          </button>
        </div>
      ) : null}

      {status && (
        <div className="p-4 bg-gray-100 rounded">
          <strong>Status: </strong> {status}
        </div>
      )}
    </div>
  );
}
