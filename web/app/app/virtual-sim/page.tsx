import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { TelegramOtpPanel } from "@/components/app/telegram-otp-panel";
import { creditState } from "@/lib/credits";
import { listCountries } from "@/lib/fivesim";
import {
  DEFAULT_OTP_SERVICE,
  OTP_SERVICES,
  isKnownOtpService,
  otpService,
} from "@/lib/otp-services";
import { getUser } from "@/lib/supabase/server";
import { listTelegramOtpOrders } from "@/lib/vrnum";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Virtual SIM" };

/**
 * Výber platformy ide cez URL, nie cez stav v prehliadači.
 *
 * Katalóg cien musí prísť zo servera pre KAŽDÚ platformu zvlášť (Instagram má
 * iné ceny než Telegram), takže prepnutie je aj tak nové načítanie. Query
 * parameter to rieši bez jediného riadku klientskeho kódu — a navyše sa dá
 * poslať odkaz priamo na WhatsApp čísla.
 */
export default async function VirtualSimPage({
  searchParams,
}: {
  searchParams: Promise<{ service?: string }>;
}) {
  const user = await getUser();
  if (!user) redirect("/login");

  const requested = (await searchParams).service ?? "";
  const service = isKnownOtpService(requested) ? requested : DEFAULT_OTP_SERVICE;

  const [credit, orders, catalog] = await Promise.all([
    creditState(),
    listTelegramOtpOrders(user.id),
    listCountries(service)
      .then((countries) => ({ countries, error: "" }))
      .catch((error: unknown) => {
        console.error("5sim catalog unavailable", error instanceof Error ? error.message : error);
        return { countries: [], error: "The live country catalog is temporarily unavailable." };
      }),
  ]);

  return (
    <>
      <div className="mb-4">
        <p className="mb-2.5 text-[11px] tracking-[0.12em] text-[var(--app-text-4)] uppercase">
          What are you verifying
        </p>
        <div className="flex flex-wrap gap-2">
          {OTP_SERVICES.map((item) => {
            const active = item.id === service;
            return (
              <Link
                key={item.id}
                href={`/app/virtual-sim?service=${item.id}`}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "app-tap rounded-xl border px-4 py-2.5 transition-colors",
                  active
                    ? "border-[var(--app-text)] bg-[var(--app-surface)]"
                    : "border-[var(--app-border)] hover:border-[var(--app-border-strong)]",
                )}
              >
                <span
                  className={cn(
                    "block text-[13.5px]",
                    active ? "font-medium text-[var(--app-text)]" : "text-[var(--app-text-2)]",
                  )}
                >
                  {item.name}
                </span>
              </Link>
            );
          })}
        </div>
      </div>

      <TelegramOtpPanel
        countries={catalog.countries}
        initialOrders={orders}
        initialBalance={credit.balance}
        catalogError={catalog.error}
        service={service}
        serviceName={otpService(service)?.name ?? "Telegram"}
      />
    </>
  );
}
