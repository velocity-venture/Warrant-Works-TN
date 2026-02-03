"use client";

import { useState, useCallback } from "react";
import {
  Upload,
  FileText,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Loader2,
  Download,
  RefreshCw,
} from "lucide-react";

interface AnalysisResult {
  compliant: boolean;
  score: number;
  issues: Issue[];
  suggestions: string[];
  documentType: string;
  extractedData: Record<string, string>;
}

interface Issue {
  severity: "error" | "warning" | "info";
  field: string;
  message: string;
  suggestion?: string;
}

const mockAnalysis: AnalysisResult = {
  compliant: false,
  score: 78,
  documentType: "Arrest Warrant",
  issues: [
    {
      severity: "error",
      field: "Probable Cause Statement",
      message: "Probable cause statement is missing specific facts supporting the alleged offense.",
      suggestion: "Include specific dates, times, and factual observations that establish probable cause.",
    },
    {
      severity: "warning",
      field: "Offense Code",
      message: "TCA citation format may be incorrect. Found '39-14-103' but expected 'T.C.A. § 39-14-103'.",
      suggestion: "Use full citation format: T.C.A. § [title]-[chapter]-[section]",
    },
    {
      severity: "info",
      field: "Defendant Address",
      message: "Defendant address is incomplete (missing ZIP code).",
      suggestion: "Include complete mailing address with ZIP code for service purposes.",
    },
  ],
  suggestions: [
    "Add witness names if available to strengthen probable cause.",
    "Include the specific value of property for theft charges.",
    "Verify defendant's date of birth against state records.",
  ],
  extractedData: {
    "Defendant Name": "John Michael Smith",
    "Date of Birth": "05/15/1985",
    "Offense": "Theft of Property over $1,000",
    "Offense Date": "01/28/2024",
    "Officer": "Deputy James Wilson #4521",
    "Agency": "Tipton County Sheriff's Office",
  },
};

export default function AnalyzePage() {
  const [file, setFile] = useState<File | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
      setResult(null);
    }
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setResult(null);
    }
  };

  const handleAnalyze = async () => {
    if (!file) return;

    setAnalyzing(true);
    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 3000));
    setResult(mockAnalysis);
    setAnalyzing(false);
  };

  const severityConfig = {
    error: { icon: XCircle, color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/30" },
    warning: { icon: AlertTriangle, color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/30" },
    info: { icon: CheckCircle, color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/30" },
  };

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Upload & Analyze</h1>
        <p className="text-slate-400">
          Upload a document to check AOC compliance and identify issues
        </p>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Upload Section */}
        <div className="space-y-6">
          {/* Drop Zone */}
          <div
            className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
              dragActive
                ? "border-blue-500 bg-blue-500/5"
                : file
                ? "border-green-500 bg-green-500/5"
                : "border-slate-700 hover:border-slate-600"
            }`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <input
              type="file"
              accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
              onChange={handleFileChange}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
            <div className="space-y-4">
              <div className="w-16 h-16 bg-slate-800 rounded-xl flex items-center justify-center mx-auto">
                {file ? (
                  <FileText className="w-8 h-8 text-green-400" />
                ) : (
                  <Upload className="w-8 h-8 text-slate-400" />
                )}
              </div>
              {file ? (
                <>
                  <p className="text-white font-medium">{file.name}</p>
                  <p className="text-slate-400 text-sm">
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                </>
              ) : (
                <>
                  <p className="text-white font-medium">
                    Drop your document here or click to browse
                  </p>
                  <p className="text-slate-400 text-sm">
                    Supports PDF, DOC, DOCX, PNG, JPG (max 10MB)
                  </p>
                </>
              )}
            </div>
          </div>

          {/* Analyze Button */}
          <button
            onClick={handleAnalyze}
            disabled={!file || analyzing}
            className="w-full py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-500 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {analyzing ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Analyzing Document...
              </>
            ) : (
              <>
                <CheckCircle className="w-5 h-5" />
                Analyze for Compliance
              </>
            )}
          </button>

          {/* Document Types */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
            <h3 className="font-semibold text-white mb-4">Supported Document Types</h3>
            <div className="space-y-3">
              {[
                { name: "Arrest Warrant", desc: "Standard TN arrest warrant" },
                { name: "Affidavit of Complaint", desc: "Sworn probable cause statement" },
                { name: "Criminal Summons", desc: "Misdemeanor notice to appear" },
                { name: "Search Warrant", desc: "Property search authorization" },
              ].map((type) => (
                <div
                  key={type.name}
                  className="flex items-center gap-3 p-3 bg-slate-800/50 rounded-lg"
                >
                  <FileText className="w-5 h-5 text-blue-400" />
                  <div>
                    <p className="text-sm font-medium text-white">{type.name}</p>
                    <p className="text-xs text-slate-500">{type.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Results Section */}
        <div className="space-y-6">
          {result ? (
            <>
              {/* Score Card */}
              <div
                className={`p-6 rounded-xl border ${
                  result.compliant
                    ? "bg-green-500/10 border-green-500/30"
                    : "bg-red-500/10 border-red-500/30"
                }`}
              >
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <p className="text-sm text-slate-400">Compliance Score</p>
                    <p
                      className={`text-4xl font-bold ${
                        result.compliant ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {result.score}%
                    </p>
                  </div>
                  <div
                    className={`w-16 h-16 rounded-full flex items-center justify-center ${
                      result.compliant ? "bg-green-500/20" : "bg-red-500/20"
                    }`}
                  >
                    {result.compliant ? (
                      <CheckCircle className="w-8 h-8 text-green-400" />
                    ) : (
                      <AlertTriangle className="w-8 h-8 text-red-400" />
                    )}
                  </div>
                </div>
                <p className="text-white font-medium">
                  {result.compliant
                    ? "Document meets AOC compliance standards"
                    : `${result.issues.filter((i) => i.severity === "error").length} issues must be resolved before filing`}
                </p>
              </div>

              {/* Extracted Data */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <h3 className="font-semibold text-white mb-4">Extracted Information</h3>
                <p className="text-sm text-blue-400 mb-4">
                  Document Type: {result.documentType}
                </p>
                <div className="space-y-2">
                  {Object.entries(result.extractedData).map(([key, value]) => (
                    <div
                      key={key}
                      className="flex justify-between py-2 border-b border-slate-800 last:border-0"
                    >
                      <span className="text-sm text-slate-400">{key}</span>
                      <span className="text-sm text-white font-medium">{value}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Issues */}
              {result.issues.length > 0 && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                  <h3 className="font-semibold text-white mb-4">
                    Issues Found ({result.issues.length})
                  </h3>
                  <div className="space-y-3">
                    {result.issues.map((issue, i) => {
                      const config = severityConfig[issue.severity];
                      return (
                        <div
                          key={i}
                          className={`p-4 rounded-lg border ${config.bg} ${config.border}`}
                        >
                          <div className="flex items-start gap-3">
                            <config.icon className={`w-5 h-5 mt-0.5 ${config.color}`} />
                            <div className="flex-1">
                              <p className="text-sm font-medium text-white">{issue.field}</p>
                              <p className="text-sm text-slate-400 mt-1">{issue.message}</p>
                              {issue.suggestion && (
                                <p className="text-xs text-blue-400 mt-2">
                                  💡 {issue.suggestion}
                                </p>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-3">
                <button className="flex-1 py-2 bg-slate-800 text-white rounded-lg font-medium hover:bg-slate-700 transition flex items-center justify-center gap-2">
                  <Download className="w-4 h-4" />
                  Download Report
                </button>
                <button
                  onClick={() => {
                    setFile(null);
                    setResult(null);
                  }}
                  className="flex-1 py-2 border border-slate-700 text-white rounded-lg font-medium hover:bg-slate-800 transition flex items-center justify-center gap-2"
                >
                  <RefreshCw className="w-4 h-4" />
                  Analyze Another
                </button>
              </div>
            </>
          ) : (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center">
              <div className="w-16 h-16 bg-slate-800 rounded-xl flex items-center justify-center mx-auto mb-4">
                <FileText className="w-8 h-8 text-slate-500" />
              </div>
              <h3 className="text-lg font-medium text-white mb-2">No Document Analyzed</h3>
              <p className="text-slate-400 text-sm">
                Upload a document and click "Analyze" to check compliance
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
