import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { TelegramOtpPanel } from "@/components/app/telegram-otp-panel";
import { creditState } from "@/lib/credits";
import { getUser } from "@/lib/supabase/server";
import { listTelegramCountries, listTelegramOtpOrders } from "@/lib/vrnum";

export const metadata: Metadata = { title: "Virtual SIM" };

export default async function VirtualSimPage() {
  const user = await getUser();
  if (!user) redirect("/login");

  const [credit, orders, catalog] = await Promise.all([
    creditState(),
    listTelegramOtpOrders(user.id),
    listTelegramCountries()
      .then((countries) => ({ countries, error: "" }))
      .catch((error: unknown) => {
        console.error("VRNUM catalog unavailable", error instanceof Error ? error.message : error);
        return { countries: [], error: "The live country catalog is temporarily unavailable." };
      }),
  ]);

  return (
    <TelegramOtpPanel
      countries={catalog.countries}
      initialOrders={orders}
      initialBalance={credit.balance}
      catalogError={catalog.error}
    />
  );
}
