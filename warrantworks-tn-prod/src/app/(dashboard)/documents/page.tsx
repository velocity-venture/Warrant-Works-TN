"use client";

import { useState } from "react";
import {
  FileText,
  Search,
  Filter,
  Download,
  Eye,
  MoreVertical,
  CheckCircle,
  AlertTriangle,
  Clock,
  Calendar,
} from "lucide-react";

interface Document {
  id: string;
  type: "Arrest Warrant" | "Affidavit" | "Criminal Summons";
  defendant: string;
  officer: string;
  badge: string;
  status: "Compliant" | "Pending Review" | "Issues Found" | "Filed";
  createdAt: string;
  offense: string;
}

const documents: Document[] = [
  {
    id: "W-2024-0147",
    type: "Arrest Warrant",
    defendant: "Smith, John M.",
    officer: "Dep. James Wilson",
    badge: "#4521",
    status: "Compliant",
    createdAt: "2024-02-03T14:30:00",
    offense: "Theft of Property > $1,000",
  },
  {
    id: "A-2024-0203",
    type: "Affidavit",
    defendant: "Williams, Marcus T.",
    officer: "Dep. Sarah Davis",
    badge: "#3892",
    status: "Pending Review",
    createdAt: "2024-02-03T11:15:00",
    offense: "Aggravated Assault",
  },
  {
    id: "S-2024-0198",
    type: "Criminal Summons",
    defendant: "Brown, Robert L.",
    officer: "Dep. Michael Miller",
    badge: "#2156",
    status: "Filed",
    createdAt: "2024-02-02T16:45:00",
    offense: "Disorderly Conduct",
  },
  {
    id: "W-2024-0145",
    type: "Arrest Warrant",
    defendant: "Garcia, Thomas A.",
    officer: "Dep. William Johnson",
    badge: "#4102",
    status: "Issues Found",
    createdAt: "2024-02-02T09:20:00",
    offense: "Domestic Assault",
  },
  {
    id: "A-2024-0201",
    type: "Affidavit",
    defendant: "Davis, Jennifer K.",
    officer: "Dep. James Wilson",
    badge: "#4521",
    status: "Compliant",
    createdAt: "2024-02-01T13:00:00",
    offense: "Vandalism > $500",
  },
  {
    id: "W-2024-0143",
    type: "Arrest Warrant",
    defendant: "Martinez, Carlos R.",
    officer: "Dep. Lisa Anderson",
    badge: "#3567",
    status: "Filed",
    createdAt: "2024-02-01T10:30:00",
    offense: "DUI - First Offense",
  },
  {
    id: "S-2024-0195",
    type: "Criminal Summons",
    defendant: "Taylor, Brandon J.",
    officer: "Dep. Robert Clark",
    badge: "#2890",
    status: "Compliant",
    createdAt: "2024-01-31T15:15:00",
    offense: "Simple Possession",
  },
  {
    id: "W-2024-0141",
    type: "Arrest Warrant",
    defendant: "Jackson, David M.",
    officer: "Dep. Sarah Davis",
    badge: "#3892",
    status: "Filed",
    createdAt: "2024-01-31T08:45:00",
    offense: "Burglary",
  },
];

const statusConfig = {
  Compliant: {
    icon: CheckCircle,
    color: "text-green-400",
    bg: "bg-green-500/10",
    border: "border-green-500/30",
  },
  "Pending Review": {
    icon: Clock,
    color: "text-yellow-400",
    bg: "bg-yellow-500/10",
    border: "border-yellow-500/30",
  },
  "Issues Found": {
    icon: AlertTriangle,
    color: "text-red-400",
    bg: "bg-red-500/10",
    border: "border-red-500/30",
  },
  Filed: {
    icon: CheckCircle,
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500/30",
  },
};

const typeColors = {
  "Arrest Warrant": "text-red-400 border-red-500/30",
  Affidavit: "text-purple-400 border-purple-500/30",
  "Criminal Summons": "text-blue-400 border-blue-500/30",
};

export default function DocumentsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  const filteredDocs = documents.filter((doc) => {
    const matchesSearch =
      doc.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      doc.defendant.toLowerCase().includes(searchQuery.toLowerCase()) ||
      doc.officer.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = !statusFilter || doc.status === statusFilter;
    const matchesType = !typeFilter || doc.type === typeFilter;
    return matchesSearch && matchesStatus && matchesType;
  });

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) {
      return `Today, ${date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;
    } else if (days === 1) {
      return `Yesterday, ${date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;
    } else {
      return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    }
  };

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Documents</h1>
          <p className="text-slate-400">View and manage all court documents</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Calendar className="w-4 h-4" />
          Showing {filteredDocs.length} of {documents.length} documents
        </div>
      </div>

      {/* Filters */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div className="flex flex-col md:flex-row gap-4">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              type="text"
              placeholder="Search by ID, defendant, or officer..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Status Filter */}
          <select
            value={statusFilter || ""}
            onChange={(e) => setStatusFilter(e.target.value || null)}
            className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
          >
            <option value="">All Statuses</option>
            <option value="Compliant">Compliant</option>
            <option value="Pending Review">Pending Review</option>
            <option value="Issues Found">Issues Found</option>
            <option value="Filed">Filed</option>
          </select>

          {/* Type Filter */}
          <select
            value={typeFilter || ""}
            onChange={(e) => setTypeFilter(e.target.value || null)}
            className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
          >
            <option value="">All Types</option>
            <option value="Arrest Warrant">Arrest Warrant</option>
            <option value="Affidavit">Affidavit</option>
            <option value="Criminal Summons">Criminal Summons</option>
          </select>
        </div>
      </div>

      {/* Documents Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-800">
                <th className="text-left p-4 text-sm font-medium text-slate-400">Document</th>
                <th className="text-left p-4 text-sm font-medium text-slate-400">Defendant</th>
                <th className="text-left p-4 text-sm font-medium text-slate-400">Offense</th>
                <th className="text-left p-4 text-sm font-medium text-slate-400">Officer</th>
                <th className="text-left p-4 text-sm font-medium text-slate-400">Status</th>
                <th className="text-left p-4 text-sm font-medium text-slate-400">Created</th>
                <th className="text-left p-4 text-sm font-medium text-slate-400">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredDocs.map((doc) => {
                const status = statusConfig[doc.status];
                return (
                  <tr
                    key={doc.id}
                    className="border-b border-slate-800/50 hover:bg-slate-800/30 transition"
                  >
                    <td className="p-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-slate-800 rounded-lg flex items-center justify-center">
                          <FileText className="w-5 h-5 text-slate-400" />
                        </div>
                        <div>
                          <p className="font-medium text-white">{doc.id}</p>
                          <span
                            className={`inline-block px-2 py-0.5 text-xs font-medium rounded border ${
                              typeColors[doc.type]
                            }`}
                          >
                            {doc.type}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="p-4">
                      <p className="text-white">{doc.defendant}</p>
                    </td>
                    <td className="p-4">
                      <p className="text-slate-400 text-sm">{doc.offense}</p>
                    </td>
                    <td className="p-4">
                      <p className="text-white text-sm">{doc.officer}</p>
                      <p className="text-slate-500 text-xs">{doc.badge}</p>
                    </td>
                    <td className="p-4">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full border ${status.bg} ${status.border} ${status.color}`}
                      >
                        <status.icon className="w-3 h-3" />
                        {doc.status}
                      </span>
                    </td>
                    <td className="p-4">
                      <p className="text-slate-400 text-sm">{formatDate(doc.createdAt)}</p>
                    </td>
                    <td className="p-4">
                      <div className="flex items-center gap-1">
                        <button className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition">
                          <Eye className="w-4 h-4" />
                        </button>
                        <button className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition">
                          <Download className="w-4 h-4" />
                        </button>
                        <button className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition">
                          <MoreVertical className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {filteredDocs.length === 0 && (
          <div className="p-8 text-center">
            <FileText className="w-12 h-12 text-slate-600 mx-auto mb-4" />
            <p className="text-slate-400">No documents found matching your criteria</p>
          </div>
        )}
      </div>

      {/* Stats Footer */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Total Documents", value: documents.length },
          { label: "Compliant", value: documents.filter((d) => d.status === "Compliant").length },
          { label: "Pending Review", value: documents.filter((d) => d.status === "Pending Review").length },
          { label: "Issues Found", value: documents.filter((d) => d.status === "Issues Found").length },
        ].map((stat) => (
          <div
            key={stat.label}
            className="p-4 bg-slate-900 border border-slate-800 rounded-xl text-center"
          >
            <p className="text-2xl font-bold text-white">{stat.value}</p>
            <p className="text-xs text-slate-400">{stat.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
