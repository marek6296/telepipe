import type { ReactNode } from "react";

import { LEGAL_READY, LEGAL_UPDATED, OPERATOR, contactLines } from "@/lib/legal";

/**
 * Spoločný rám pre Privacy, Terms a Contact.
 *
 * Právne dokumenty majú byť nudné a čitateľné — žiadne animácie, žiadne
 * gradienty. Jediná ozdoba je typografia, lebo tieto stránky číta človek,
 * ktorý niečo hľadá, nie ktorý sa nechá presviedčať.
 */
export function LegalPage({
  title,
  intro,
  children,
}: {
  title: string;
  intro: string;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-3xl px-6 pt-32 pb-24">
      <h1 className="text-[30px] leading-tight font-medium text-white sm:text-[36px]">{title}</h1>
      <p className="mt-4 text-[15px] leading-relaxed text-white/55">{intro}</p>
      <p className="mt-3 text-[13px] text-white/30">Last updated: {LEGAL_UPDATED}</p>

      {!LEGAL_READY && (
        // Priznať chýbajúce údaje, ale NEspochybniť samotný dokument. Podmienky,
        // ktoré o sebe tvrdia, že neplatia, sú horšie než žiadne — a to, ako
        // narábame s dátami, platí bez ohľadu na to, či je doplnené IČO.
        <div className="mt-8 rounded-xl border border-white/[0.1] bg-white/[0.03] px-5 py-4">
          <p className="text-[13.5px] leading-relaxed text-white/55">
            Our registration details and contact address are being finalised and will be
            published in the Operator section below. Everything else on this page applies
            today.
          </p>
        </div>
      )}

      <div className="legal-body mt-10">{children}</div>

      <OperatorBlock />
    </div>
  );
}

function OperatorBlock() {
  const contacts = contactLines();

  return (
    <section className="mt-14 rounded-xl border border-white/[0.08] px-6 py-5">
      <h2 className="text-[13px] font-medium tracking-[0.1em] text-white/40 uppercase">
        Operator
      </h2>
      {LEGAL_READY ? (
        <div className="mt-3 space-y-1 text-[14px] leading-relaxed text-white/70">
          <p className="text-white">{OPERATOR.legalName}</p>
          <p>{OPERATOR.address}</p>
          <p>{OPERATOR.registration}</p>
          {contacts.map((line) => (
            <p key={line.label}>
              <span className="text-white/40">{line.label}: </span>
              {line.value}
            </p>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-[14px] leading-relaxed text-white/45">
          Registration details and contact address will be published here.
        </p>
      )}
    </section>
  );
}

/** Nadpis sekcie v právnom texte. */
export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-9 first:mt-0">
      <h2 className="text-[17px] font-medium text-white">{title}</h2>
      <div className="mt-3 space-y-3 text-[14.5px] leading-relaxed text-white/60">{children}</div>
    </section>
  );
}

/** Tabuľka „aké údaje / načo / ako dlho". Konkrétnosť je tu celá hodnota. */
export function DataTable({ rows }: { rows: [string, string, string][] }) {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[520px] text-left text-[13.5px]">
        <thead>
          <tr className="border-b border-white/[0.08] text-white/40">
            <th className="py-2 pr-4 font-normal">Data</th>
            <th className="py-2 pr-4 font-normal">Why</th>
            <th className="py-2 font-normal">Kept for</th>
          </tr>
        </thead>
        <tbody className="text-white/60">
          {rows.map(([what, why, kept]) => (
            <tr key={what} className="border-b border-white/[0.05] last:border-b-0">
              <td className="py-2.5 pr-4 text-white/80">{what}</td>
              <td className="py-2.5 pr-4">{why}</td>
              <td className="py-2.5">{kept}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
