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
};

export default nextConfig;
