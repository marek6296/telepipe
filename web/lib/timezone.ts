/**
 * Overenie časovej zóny — prísnejšie než `Intl`, lebo zónu číta Python.
 *
 * `behavior.active_tz` skončí vo workeri v `ZoneInfo(...)`
 * (`userbot.py:323`, `:1808`) a tam sa rozhoduje jej celý deň. Lenže tie dve
 * knižnice sa nezhodujú: `Intl` v Node prijme aj „PST" a „EST", `ZoneInfo`
 * na „PST" hodí `ZoneInfoNotFoundError` — a to pri KAŽDEJ odpovedi, nie raz.
 *
 * Preto trváme na tvare `Oblasť/Miesto`. Nepoužívame `Intl.supportedValuesOf`,
 * hoci by to bol krajší zoznam: vracia len kanonické zóny, takže by vyhodil
 * `Europe/Kyiv` aj `Asia/Kolkata` — obe platné a obe `ZoneInfo` pozná (jedna
 * z nich je priamo v selecte na karte Behavior).
 */
export function isTimeZone(value: string): boolean {
  const zone = value.trim();
  // „PST", „EST", „UTC", „PST8PDT" — Intl ich vezme, ZoneInfo časť z nich nie.
  if (!/^[A-Za-z][A-Za-z0-9_+-]*(\/[A-Za-z0-9_+-]+)+$/.test(zone)) return false;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: zone });
    return true;
  } catch {
    return false;
  }
}
