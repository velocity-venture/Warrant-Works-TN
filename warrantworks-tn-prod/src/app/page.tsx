"use client";

import { useState } from "react";
import Link from "next/link";
import {
  FileText,
  Shield,
  CheckCircle,
  ArrowRight,
  Scale,
  Zap,
  Lock,
  Clock,
  Users,
  Building,
} from "lucide-react";

export default function Home() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Header */}
      <header className="border-b border-slate-800">
        <div className="max-w-6xl mx-auto px-6 py-4 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
              <Scale className="w-5 h-5 text-white" />
            </div>
            <div>
              <span className="font-bold text-lg">WarrantWorks</span>
              <span className="text-blue-400 text-sm ml-1">TN</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="text-slate-400 hover:text-white transition">
              Dashboard
            </Link>
            <a
              href="#waitlist"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-500 transition"
            >
              Request Demo
            </a>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="py-24 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-block px-4 py-1.5 bg-blue-500/10 border border-blue-500/30 rounded-full text-blue-400 text-sm font-medium mb-8">
            AI-Powered Court Document Standardization
          </div>
          <h1 className="text-5xl md:text-6xl font-bold leading-tight mb-6">
            Warrants Done Right.
            <br />
            <span className="text-blue-400">Every Time.</span>
          </h1>
          <p className="text-xl text-slate-400 mb-10 max-w-2xl mx-auto">
            WarrantWorks TN ensures your arrest warrants, affidavits, and criminal summons
            meet AOC compliance standards. AI-powered analysis catches errors before they
            become problems.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="#waitlist"
              className="px-8 py-4 bg-blue-600 text-white rounded-xl font-semibold text-lg hover:bg-blue-500 transition"
            >
              Schedule Demo
            </a>
            <Link
              href="/dashboard"
              className="px-8 py-4 border border-slate-700 rounded-xl font-semibold text-lg hover:bg-slate-800 transition"
            >
              Try It Now
            </Link>
          </div>
        </div>
      </section>

      {/* Problem Statement */}
      <section className="py-20 px-6 bg-slate-900/50">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold mb-6">The Problem with Paper</h2>
          <div className="grid md:grid-cols-3 gap-8 mt-12">
            {[
              {
                stat: "23%",
                label: "of warrants contain errors",
                desc: "Missing signatures, wrong codes, incomplete information",
              },
              {
                stat: "4+ hrs",
                label: "wasted per week on corrections",
                desc: "Back-and-forth between officers and clerks",
              },
              {
                stat: "$0",
                label: "in standardization tools",
                desc: "Most agencies rely on Word templates and hope",
              },
            ].map((item, i) => (
              <div key={i} className="p-6 bg-slate-800/50 rounded-xl border border-slate-700">
                <p className="text-4xl font-bold text-red-400 mb-2">{item.stat}</p>
                <p className="text-white font-medium mb-2">{item.label}</p>
                <p className="text-slate-400 text-sm">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-16">
            How WarrantWorks TN Helps
          </h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[
              {
                icon: FileText,
                title: "Document Analysis",
                desc: "Upload any warrant document. Our AI analyzes it against AOC standards and flags issues instantly.",
              },
              {
                icon: CheckCircle,
                title: "Compliance Checking",
                desc: "Real-time validation against Tennessee AOC requirements. Never file a non-compliant document again.",
              },
              {
                icon: Zap,
                title: "Auto-Generation",
                desc: "Generate compliant warrants, affidavits, and summons from structured input. Error-free every time.",
              },
              {
                icon: Shield,
                title: "Audit Trail",
                desc: "Complete history of document creation, edits, and approvals. Full accountability.",
              },
              {
                icon: Lock,
                title: "Secure by Design",
                desc: "CJIS-compliant security. End-to-end encryption. Your data never leaves your control.",
              },
              {
                icon: Clock,
                title: "Time Savings",
                desc: "Reduce document preparation time by 60%. Officers spend time policing, not paperwork.",
              },
            ].map((feature, i) => (
              <div
                key={i}
                className="p-6 bg-slate-900 border border-slate-800 rounded-2xl hover:border-blue-500/50 transition"
              >
                <div className="w-12 h-12 bg-blue-500/10 rounded-lg flex items-center justify-center mb-4">
                  <feature.icon className="w-6 h-6 text-blue-400" />
                </div>
                <h3 className="text-xl font-semibold mb-2">{feature.title}</h3>
                <p className="text-slate-400">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Document Types */}
      <section className="py-24 px-6 bg-slate-900/50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-4">Supported Documents</h2>
          <p className="text-slate-400 text-center mb-12">
            WarrantWorks TN supports all standard Tennessee court documents
          </p>
          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                name: "Arrest Warrant",
                desc: "Standard arrest warrant with probable cause statement",
                icon: "⚖️",
              },
              {
                name: "Affidavit of Complaint",
                desc: "Sworn statement establishing probable cause",
                icon: "📋",
              },
              {
                name: "Criminal Summons",
                desc: "Notice to appear for misdemeanor charges",
                icon: "📨",
              },
            ].map((doc, i) => (
              <div
                key={i}
                className="p-6 bg-slate-800 rounded-xl border border-slate-700 text-center"
              >
                <div className="text-4xl mb-4">{doc.icon}</div>
                <h3 className="text-lg font-semibold mb-2">{doc.name}</h3>
                <p className="text-slate-400 text-sm">{doc.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="py-24 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold mb-4">Simple Pricing</h2>
          <p className="text-slate-400 mb-12">Per-agency pricing based on size</p>
          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                name: "Small Agency",
                price: "$199",
                desc: "Up to 25 officers",
                features: ["Unlimited documents", "AI analysis", "Email support"],
              },
              {
                name: "Medium Agency",
                price: "$399",
                desc: "26-100 officers",
                features: [
                  "Everything in Small",
                  "API access",
                  "Priority support",
                  "Custom templates",
                ],
                popular: true,
              },
              {
                name: "Large Agency",
                price: "Custom",
                desc: "100+ officers",
                features: [
                  "Everything in Medium",
                  "Dedicated support",
                  "On-premise option",
                  "Training included",
                ],
              },
            ].map((plan, i) => (
              <div
                key={i}
                className={`p-6 rounded-2xl border ${
                  plan.popular
                    ? "bg-blue-500/10 border-blue-500/30"
                    : "bg-slate-900 border-slate-800"
                }`}
              >
                {plan.popular && (
                  <div className="text-blue-400 text-sm font-medium mb-2">Most Popular</div>
                )}
                <h3 className="text-xl font-semibold">{plan.name}</h3>
                <div className="text-4xl font-bold my-4">
                  {plan.price}
                  {plan.price !== "Custom" && (
                    <span className="text-lg text-slate-400">/mo</span>
                  )}
                </div>
                <p className="text-slate-400 text-sm mb-6">{plan.desc}</p>
                <ul className="text-left space-y-2">
                  {plan.features.map((f, j) => (
                    <li key={j} className="flex items-center gap-2 text-sm">
                      <CheckCircle className="w-4 h-4 text-blue-400" />
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section
        id="waitlist"
        className="py-24 px-6 bg-gradient-to-b from-transparent to-blue-500/5"
      >
        <div className="max-w-xl mx-auto text-center">
          <h2 className="text-3xl font-bold mb-4">Ready to Modernize Your Warrants?</h2>
          <p className="text-slate-400 mb-8">
            Join Tennessee agencies using WarrantWorks TN to ensure compliance and save time.
          </p>
          {submitted ? (
            <div className="p-6 bg-green-500/10 border border-green-500/30 rounded-xl">
              <p className="text-green-400 font-medium">
                ✓ Request received! We'll contact you within 24 hours.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Your work email"
                required
                className="flex-1 px-4 py-3 bg-slate-900 border border-slate-700 rounded-xl focus:outline-none focus:border-blue-500"
              />
              <button
                type="submit"
                className="px-6 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-500 transition"
              >
                Request Demo
              </button>
            </form>
          )}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-800 py-12 px-6">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-600 rounded flex items-center justify-center">
              <Scale className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold">WarrantWorks TN</span>
          </div>
          <p className="text-slate-500 text-sm">
            © 2026 Velocity Venture Holdings, LLC. A SAYADA Product.
          </p>
        </div>
      </footer>
    </div>
  );
}
