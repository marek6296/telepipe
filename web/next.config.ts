import type { NextConfig } from "next";

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
