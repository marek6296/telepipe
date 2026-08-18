import { ImageResponse } from "next/og";

export const alt = "Telepipe — AI Telegram chat automation for creators and agencies";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          position: "relative",
          overflow: "hidden",
          background: "#050505",
          color: "#fafafa",
          padding: "72px 82px",
          flexDirection: "column",
          justifyContent: "space-between",
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            backgroundImage:
              "linear-gradient(rgba(255,255,255,.055) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.055) 1px, transparent 1px), radial-gradient(circle at 70% 45%, rgba(255,255,255,.13), transparent 36%)",
            backgroundSize: "64px 64px, 64px 64px, 100% 100%",
          }}
        />

        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div
            style={{
              display: "flex",
              width: 42,
              height: 42,
              borderRadius: 12,
              border: "1px solid rgba(255,255,255,.2)",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 22,
            }}
          >
            T
          </div>
          <div style={{ display: "flex", fontSize: 30, fontWeight: 700 }}>Telepipe</div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", maxWidth: 930 }}>
          <div
            style={{
              display: "flex",
              color: "rgba(255,255,255,.48)",
              fontSize: 20,
              textTransform: "uppercase",
              letterSpacing: ".22em",
              marginBottom: 25,
            }}
          >
            AI chat automation
          </div>
          <div
            style={{
              display: "flex",
              fontSize: 66,
              lineHeight: 1.06,
              letterSpacing: "-.045em",
              fontWeight: 700,
            }}
          >
            Telegram conversations that keep moving.
          </div>
          <div
            style={{
              display: "flex",
              marginTop: 26,
              color: "rgba(255,255,255,.52)",
              fontSize: 25,
            }}
          >
            Persistent persona · memory · voice · creator conversion flow
          </div>
        </div>

        <div style={{ display: "flex", color: "rgba(255,255,255,.35)", fontSize: 19 }}>
          telepipe.me
        </div>
      </div>
    ),
    size,
  );
}
