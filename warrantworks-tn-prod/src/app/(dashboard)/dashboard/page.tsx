"use client";

import Link from "next/link";
import {
  FileText,
  Upload,
  CheckCircle,
  AlertTriangle,
  Clock,
  TrendingUp,
  ArrowRight,
  FileCheck,
} from "lucide-react";

const stats = [
  { name: "Documents This Month", value: "47", icon: FileText, change: "+12% from last month" },
  { name: "Compliance Rate", value: "98%", icon: CheckCircle, change: "Up from 87%" },
  { name: "Avg Processing Time", value: "2.3 min", icon: Clock, change: "-45% improvement" },
  { name: "Issues Caught", value: "23", icon: AlertTriangle, change: "Before filing" },
];

const recentDocuments = [
  {
    id: "W-2024-0147",
    type: "Arrest Warrant",
    defendant: "J. Smith",
    officer: "Dep. Johnson",
    status: "Compliant",
    date: "Today, 2:30 PM",
  },
  {
    id: "A-2024-0203",
    type: "Affidavit",
    defendant: "M. Williams",
    officer: "Dep. Davis",
    status: "Pending Review",
    date: "Today, 11:15 AM",
  },
  {
    id: "S-2024-0198",
    type: "Criminal Summons",
    defendant: "R. Brown",
    officer: "Dep. Miller",
    status: "Compliant",
    date: "Yesterday",
  },
  {
    id: "W-2024-0145",
    type: "Arrest Warrant",
    defendant: "T. Garcia",
    officer: "Dep. Wilson",
    status: "Issues Found",
    date: "Yesterday",
  },
];

const statusColors: Record<string, string> = {
  Compliant: "bg-green-500/10 text-green-400 border-green-500/30",
  "Pending Review": "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  "Issues Found": "bg-red-500/10 text-red-400 border-red-500/30",
};

export default function DashboardPage() {
  return (
    <div className="p-6 lg:p-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-slate-400">
            {new Date().toLocaleDateString("en-US", {
              weekday: "long",
              year: "numeric",
              month: "long",
              day: "numeric",
            })}
          </p>
        </div>
        <Link
          href="/analyze"
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-500 transition"
        >
          <Upload className="w-4 h-4" />
          Upload Document
        </Link>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <div
            key={stat.name}
            className="p-6 bg-slate-900 border border-slate-800 rounded-xl"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-400">{stat.name}</p>
                <p className="text-3xl font-bold text-white mt-1">{stat.value}</p>
                <p className="text-xs text-slate-500 mt-1">{stat.change}</p>
              </div>
              <div className="w-12 h-12 bg-blue-500/10 rounded-lg flex items-center justify-center">
                <stat.icon className="w-6 h-6 text-blue-400" />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent Documents */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl">
          <div className="flex items-center justify-between p-6 border-b border-slate-800">
            <div>
              <h2 className="text-lg font-semibold text-white">Recent Documents</h2>
              <p className="text-sm text-slate-400">Latest processed documents</p>
            </div>
            <Link
              href="/documents"
              className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
            >
              View All <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
          <div className="divide-y divide-slate-800">
            {recentDocuments.map((doc) => (
              <div key={doc.id} className="p-4 hover:bg-slate-800/50 transition">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-slate-800 rounded-lg flex items-center justify-center">
                      <FileText className="w-5 h-5 text-slate-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-white">
                        {doc.id} — {doc.type}
                      </p>
                      <p className="text-xs text-slate-500">
                        {doc.defendant} • {doc.officer}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span
                      className={`inline-block px-2 py-1 text-xs font-medium rounded-full border ${
                        statusColors[doc.status]
                      }`}
                    >
                      {doc.status}
                    </span>
                    <p className="text-xs text-slate-500 mt-1">{doc.date}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="space-y-6">
          {/* Quick Actions Card */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Quick Actions</h2>
            <div className="grid grid-cols-2 gap-3">
              <Link
                href="/analyze"
                className="p-4 bg-slate-800/50 rounded-lg border border-slate-700 hover:border-blue-500/50 transition"
              >
                <Upload className="w-8 h-8 text-blue-400 mb-2" />
                <h3 className="font-medium text-white text-sm">Analyze Document</h3>
                <p className="text-xs text-slate-400 mt-1">Upload & check compliance</p>
              </Link>
              <Link
                href="/templates?type=warrant"
                className="p-4 bg-slate-800/50 rounded-lg border border-slate-700 hover:border-blue-500/50 transition"
              >
                <FileText className="w-8 h-8 text-blue-400 mb-2" />
                <h3 className="font-medium text-white text-sm">New Warrant</h3>
                <p className="text-xs text-slate-400 mt-1">Generate from template</p>
              </Link>
              <Link
                href="/templates?type=affidavit"
                className="p-4 bg-slate-800/50 rounded-lg border border-slate-700 hover:border-blue-500/50 transition"
              >
                <FileCheck className="w-8 h-8 text-blue-400 mb-2" />
                <h3 className="font-medium text-white text-sm">New Affidavit</h3>
                <p className="text-xs text-slate-400 mt-1">Affidavit of complaint</p>
              </Link>
              <Link
                href="/templates?type=summons"
                className="p-4 bg-slate-800/50 rounded-lg border border-slate-700 hover:border-blue-500/50 transition"
              >
                <FileText className="w-8 h-8 text-blue-400 mb-2" />
                <h3 className="font-medium text-white text-sm">Criminal Summons</h3>
                <p className="text-xs text-slate-400 mt-1">Notice to appear</p>
              </Link>
            </div>
          </div>

          {/* Compliance Overview */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Compliance Overview</h2>
            <div className="space-y-4">
              {[
                { label: "Required Fields", value: 98, color: "bg-green-500" },
                { label: "Proper Citations", value: 95, color: "bg-green-500" },
                { label: "Signature Blocks", value: 100, color: "bg-green-500" },
                { label: "Date Formats", value: 92, color: "bg-yellow-500" },
              ].map((item) => (
                <div key={item.label}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-400">{item.label}</span>
                    <span className="text-white font-medium">{item.value}%</span>
                  </div>
                  <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${item.color} rounded-full transition-all`}
                      style={{ width: `${item.value}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
