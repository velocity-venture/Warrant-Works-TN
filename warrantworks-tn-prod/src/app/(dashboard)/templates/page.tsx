"use client";

import { useState } from "react";
import { FileText, Download, Eye, Plus, Check, ChevronRight } from "lucide-react";

interface Template {
  id: string;
  name: string;
  description: string;
  type: "warrant" | "affidavit" | "summons";
  lastUsed: string;
  uses: number;
}

const templates: Template[] = [
  {
    id: "1",
    name: "Standard Arrest Warrant",
    description: "AOC-compliant arrest warrant template for all felony and misdemeanor offenses",
    type: "warrant",
    lastUsed: "Today",
    uses: 156,
  },
  {
    id: "2",
    name: "Affidavit of Complaint",
    description: "Sworn statement establishing probable cause for arrest or summons",
    type: "affidavit",
    lastUsed: "Today",
    uses: 134,
  },
  {
    id: "3",
    name: "Criminal Summons",
    description: "Notice to appear for misdemeanor charges not requiring immediate custody",
    type: "summons",
    lastUsed: "Yesterday",
    uses: 89,
  },
  {
    id: "4",
    name: "Felony Arrest Warrant",
    description: "Enhanced template for Class A-E felony offenses with special provisions",
    type: "warrant",
    lastUsed: "2 days ago",
    uses: 45,
  },
  {
    id: "5",
    name: "DUI Affidavit",
    description: "Specialized affidavit for DUI/DWI charges with BAC and field sobriety fields",
    type: "affidavit",
    lastUsed: "3 days ago",
    uses: 67,
  },
  {
    id: "6",
    name: "Domestic Violence Warrant",
    description: "Arrest warrant with victim information and bond condition provisions",
    type: "warrant",
    lastUsed: "1 week ago",
    uses: 38,
  },
];

const typeConfig = {
  warrant: { label: "Arrest Warrant", color: "bg-red-500/10 text-red-400 border-red-500/30" },
  affidavit: { label: "Affidavit", color: "bg-purple-500/10 text-purple-400 border-purple-500/30" },
  summons: { label: "Criminal Summons", color: "bg-blue-500/10 text-blue-400 border-blue-500/30" },
};

export default function TemplatesPage() {
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);

  const filteredTemplates = selectedType
    ? templates.filter((t) => t.type === selectedType)
    : templates;

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Document Templates</h1>
          <p className="text-slate-400">
            Generate compliant court documents from pre-approved templates
          </p>
        </div>
        <button className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-500 transition">
          <Plus className="w-4 h-4" />
          New Document
        </button>
      </div>

      {/* Type Filter */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setSelectedType(null)}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
            selectedType === null
              ? "bg-blue-600 text-white"
              : "bg-slate-800 text-slate-400 hover:text-white"
          }`}
        >
          All Types
        </button>
        {Object.entries(typeConfig).map(([type, config]) => (
          <button
            key={type}
            onClick={() => setSelectedType(type)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              selectedType === type
                ? "bg-blue-600 text-white"
                : "bg-slate-800 text-slate-400 hover:text-white"
            }`}
          >
            {config.label}
          </button>
        ))}
      </div>

      {/* Templates Grid */}
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredTemplates.map((template) => {
          const config = typeConfig[template.type];
          return (
            <div
              key={template.id}
              onClick={() => setSelectedTemplate(template)}
              className={`p-6 bg-slate-900 border rounded-xl cursor-pointer transition ${
                selectedTemplate?.id === template.id
                  ? "border-blue-500"
                  : "border-slate-800 hover:border-slate-700"
              }`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 bg-slate-800 rounded-lg flex items-center justify-center">
                  <FileText className="w-6 h-6 text-blue-400" />
                </div>
                <span
                  className={`px-2 py-1 text-xs font-medium rounded-full border ${config.color}`}
                >
                  {config.label}
                </span>
              </div>
              <h3 className="font-semibold text-white mb-2">{template.name}</h3>
              <p className="text-sm text-slate-400 mb-4">{template.description}</p>
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>Last used: {template.lastUsed}</span>
                <span>{template.uses} uses</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected Template Actions */}
      {selectedTemplate && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-800 border border-slate-700 rounded-xl p-4 shadow-2xl flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-500/10 rounded-lg flex items-center justify-center">
              <FileText className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p className="font-medium text-white">{selectedTemplate.name}</p>
              <p className="text-xs text-slate-400">{typeConfig[selectedTemplate.type].label}</p>
            </div>
          </div>
          <div className="h-8 w-px bg-slate-700" />
          <button className="px-4 py-2 bg-slate-700 text-white rounded-lg text-sm font-medium hover:bg-slate-600 transition flex items-center gap-2">
            <Eye className="w-4 h-4" />
            Preview
          </button>
          <button className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-500 transition flex items-center gap-2">
            Use Template
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Template Form (Would expand on click) */}
      {selectedTemplate && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mt-8">
          <h2 className="text-lg font-semibold text-white mb-6">
            Generate: {selectedTemplate.name}
          </h2>
          <div className="grid md:grid-cols-2 gap-6">
            {/* Defendant Info */}
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-blue-400 uppercase tracking-wider">
                Defendant Information
              </h3>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Full Legal Name</label>
                <input
                  type="text"
                  placeholder="Last, First Middle"
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Date of Birth</label>
                  <input
                    type="date"
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">SSN (Last 4)</label>
                  <input
                    type="text"
                    placeholder="XXXX"
                    maxLength={4}
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Address</label>
                <input
                  type="text"
                  placeholder="Street, City, State ZIP"
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>

            {/* Offense Info */}
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-blue-400 uppercase tracking-wider">
                Offense Information
              </h3>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Offense</label>
                <select className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500">
                  <option value="">Select offense...</option>
                  <option value="theft">Theft of Property (T.C.A. § 39-14-103)</option>
                  <option value="assault">Assault (T.C.A. § 39-13-101)</option>
                  <option value="dui">DUI (T.C.A. § 55-10-401)</option>
                  <option value="drugs">Simple Possession (T.C.A. § 39-17-418)</option>
                  <option value="domestic">Domestic Assault (T.C.A. § 39-13-111)</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Offense Date</label>
                  <input
                    type="date"
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Offense Time</label>
                  <input
                    type="time"
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Location of Offense</label>
                <input
                  type="text"
                  placeholder="Address or description"
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>

            {/* Probable Cause */}
            <div className="md:col-span-2 space-y-4">
              <h3 className="text-sm font-medium text-blue-400 uppercase tracking-wider">
                Probable Cause Statement
              </h3>
              <textarea
                rows={4}
                placeholder="Describe the facts and circumstances that establish probable cause..."
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 resize-none"
              />
            </div>
          </div>

          <div className="flex justify-end gap-3 mt-6 pt-6 border-t border-slate-800">
            <button className="px-4 py-2 text-slate-400 hover:text-white transition">
              Cancel
            </button>
            <button className="px-4 py-2 bg-slate-700 text-white rounded-lg font-medium hover:bg-slate-600 transition flex items-center gap-2">
              <Eye className="w-4 h-4" />
              Preview
            </button>
            <button className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-500 transition flex items-center gap-2">
              <Check className="w-4 h-4" />
              Generate Document
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
