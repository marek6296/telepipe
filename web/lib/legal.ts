/**
 * Právna identita prevádzkovateľa — JEDINÉ miesto, kde sa mení.
 *
 * Značka („TelePipe") a právna osoba nie sú to isté. Na stránke svieti značka,
 * ale v Privacy Policy aj v Terms musí byť napísané, kto peniaze naozaj prijíma
 * a kto za službu zodpovedá. To je zákonná povinnosť (GDPR čl. 13 a smernica
 * o elektronickom obchode) a nedá sa nahradiť názvom produktu.
 *
 * ⚠️ HODNOTY NIŽŠIE SÚ NEVYPLNENÉ. Kým sa nedoplnia, `LEGAL_READY` je `false`
 * a stránky to jasne priznajú namiesto toho, aby predstierali údaje, ktoré
 * nemáme. Nepravdivá identifikácia prevádzkovateľa je horšia než žiadna.
 */

export const BRAND = "TelePipe";

export type LegalOperator = {
  /** Presný názov, ako je zapísaný v registri — nie značka. */
  legalName: string;
  /** Adresa sídla / miesta podnikania. */
  address: string;
  /** IČO (a DIČ, ak je platiteľ DPH). */
  registration: string;
  /** E-mail pre výkon práv dotknutých osôb. GDPR ho v praxi predpokladá —
   *  Telegram sám nestačí, nie je z neho doručenka a dozorný orgán ho neuzná. */
  email: string;
  /** Podpora cez Telegram — doplnok k e-mailu, nie náhrada. */
  telegram: string;
};

export const OPERATOR: LegalOperator = {
  legalName: "",
  address: "",
  registration: "",
  email: "",
  telegram: "",
};

/**
 * Sú právne údaje doplnené? Kým nie, stránky sa nezaradia do sitemapy ani do
 * pätičky — inak by sme na dôveryhodnosť lákali dokumentom, ktorý ju sám nemá.
 */
export const LEGAL_READY = Boolean(
  OPERATOR.legalName && OPERATOR.address && OPERATOR.registration && OPERATOR.email,
);

/** Dátum poslednej vecnej úpravy dokumentov. Meniť pri KAŽDEJ zmene obsahu. */
export const LEGAL_UPDATED = "2026-08-19";

/** Kam sa klient obráti. Prázdne hodnoty sa nevypisujú. */
export function contactLines(): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  if (OPERATOR.email) out.push({ label: "Email", value: OPERATOR.email });
  if (OPERATOR.telegram) out.push({ label: "Telegram", value: OPERATOR.telegram });
  return out;
}
