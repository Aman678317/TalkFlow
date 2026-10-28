import { Phone, Globe, ShieldCheck } from "lucide-react";
import PhoneCallingTab from "../components/voice/PhoneCallingTab";

export default function GlobalCall() {
  return (
    <div className="mx-auto max-w-6xl p-4 lg:p-6 space-y-6">
      {/* HEADER & TOP NAVIGATION */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200/80 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#007AFF] text-white shadow-xs">
              <Phone className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
                Global Call
                <span className="rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" /> Telephony & VoIP
                </span>
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">
                Real-time two-way AI translated calling to real phone numbers (PSTN) and WhatsApp worldwide.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 shadow-2xs">
            <Globe className="h-3.5 w-3.5 text-dl-blue" />
            180+ Countries
          </span>
          <span className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 shadow-2xs">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
            E2E Encrypted VoIP
          </span>
        </div>
      </div>

      {/* DEDICATED PHONE CALLING ENGINE */}
      <PhoneCallingTab />
    </div>
  );
}
