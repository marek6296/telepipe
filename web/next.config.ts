import type { NextConfig } from "next";

/**
 * POZNÁMKA K `vercel.json` — patrí sem, lebo JSON komentáre nepovoľuje.
 *
 * `regions: ["dub1"]` nie je kozmetika. Supabase beží v `eu-west-1` (Írsko) a
 * funkcie predtým bežali v default regióne `iad1` (Washington). Namerané na
 * `/api/internal/stars-invoice` porovnaním odpovede bez DB dotazu (403) a
 * s jedným dotazom (404): jeden dotaz stál ~114 ms len na sieti. Stránka
 * s piatimi dotazmi tak čakala cez pol sekundy na Atlantik.
 *
 * A pozor: `vercel.json` má PRÍSNU schému. Kľúč `"//"` použitý ako komentár
 * zhodí celý deploy hláškou „should NOT have additional property". Preto je
 * toto vysvetlenie tu a nie tam.
 */

const nextConfig: NextConfig = {
  images: {
    // Fotky modeliek žijú vo verejnom Supabase buckete `photos`.
    remotePatterns: [
      {
        protocol: "https",
        hostname: "*.supabase.co",
        pathname: "/storage/v1/object/public/**",
      },
    ],
  },

  /**
   * Presťahované karty (`lib/model-types.ts`): fotky a konverzácie pod Telegram
   * (odchádzajú len tam a `dm_*` je telegramová história), chovanie pod Personu
   * (kto je + ako sa správa = jedna osoba). Staré ploché URL ostávajú funkčné:
   * bookmark, odkaz v maile aj otvorená karta v prehliadači.
   *
   * `permanent: false` (307) zámerne — 308 si prehliadač zapamätá navždy
   * a prípadné ďalšie sťahovanie by sa už nedalo prebiť.
   */
  async redirects() {
    return [
      {
        source: "/app/m/:id/behavior",
        destination: "/app/m/:id/persona/behavior",
        permanent: false,
      },
      {
        source: "/app/m/:id/photos",
        destination: "/app/m/:id/telegram/photos",
        permanent: false,
      },
      {
        source: "/app/m/:id/chats",
        destination: "/app/m/:id/telegram/chats",
        permanent: false,
      },
      {
        source: "/app/m/:id/chats/:chatId",
        destination: "/app/m/:id/telegram/chats/:chatId",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
