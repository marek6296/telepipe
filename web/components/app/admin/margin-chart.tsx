import type { AdminUsageDay } from "@/lib/admin";
import { usdPrecise } from "@/lib/format";

/**
 * Charged vs. Atlas cost ako čisté SVG — žiadna knižnica, žiaden client bundle.
 * Zlatý stĺpec je to, čo zaplatil klient; tmavý prekryv v jeho spodnej časti je
 * naša nákupná cena, takže zlatý zvyšok NAD ním je marža. Svetlá lomená čiara
 * kreslí maržu deň po dni.
 */
export function MarginChart({ days }: { days: AdminUsageDay[] }) {
  const max = Math.max(...days.map((day) => day.charged), 0.0001);
  const width = 100;
  const height = 34;
  const gap = 0.6;
  const barWidth = Math.max(0.6, width / days.length - gap);

  const x = (index: number) => index * (barWidth + gap);
  const y = (value: number) => height - (Math.max(value, 0) / max) * (height - 2);

  const marginLine = days
    .map((day, index) => `${(x(index) + barWidth / 2).toFixed(2)},${y(day.margin).toFixed(2)}`)
    .join(" ");

  const label = (day: AdminUsageDay) =>
    new Date(`${day.day}T00:00:00Z`).toLocaleDateString("en-US", {
      day: "numeric",
      month: "short",
      timeZone: "UTC",
    });

  return (
    <div className="px-5 pb-5 pt-4">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Charged, Atlas cost and margin per day"
        className="h-48 w-full overflow-visible"
      >
        <defs>
          <linearGradient id="admin-charged" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#e8c766" />
            <stop offset="100%" stopColor="#a8872a" />
          </linearGradient>
        </defs>

        {[0.25, 0.5, 0.75, 1].map((line) => (
          <line
            key={line}
            x1={0}
            x2={width}
            y1={height - line * (height - 2)}
            y2={height - line * (height - 2)}
            stroke="rgba(255,255,255,0.05)"
            strokeWidth={0.15}
          />
        ))}

        {days.map((day, index) => {
          const chargedHeight = Math.max(day.charged > 0 ? 0.6 : 0, height - y(day.charged));
          const costHeight = Math.max(day.atlasCost > 0 ? 0.4 : 0, height - y(day.atlasCost));
          return (
            <g key={day.day}>
              <title>
                {`${label(day)} — charged ${usdPrecise(day.charged)} · cost ${usdPrecise(
                  day.atlasCost,
                )} · margin ${usdPrecise(day.margin)}`}
              </title>
              <rect
                x={x(index)}
                y={height - chargedHeight}
                width={barWidth}
                height={chargedHeight}
                rx={0.35}
                fill="url(#admin-charged)"
                opacity={day.charged > 0 ? 1 : 0.25}
              />
              <rect
                x={x(index)}
                y={height - costHeight}
                width={barWidth}
                height={costHeight}
                rx={0.35}
                fill="#2a2210"
                opacity={0.92}
              />
            </g>
          );
        })}

        <polyline
          points={marginLine}
          fill="none"
          stroke="#f3e0a4"
          strokeWidth={0.35}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      <div className="mt-3 flex justify-between text-[10.5px] text-white/25">
        <span>{days[0] ? label(days[0]) : ""}</span>
        <span>{days[Math.floor(days.length / 2)] ? label(days[Math.floor(days.length / 2)]) : ""}</span>
        <span>{days[days.length - 1] ? label(days[days.length - 1]) : ""}</span>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-4 text-[11.5px] text-white/40">
        <Legend swatch="linear-gradient(180deg,#e8c766,#a8872a)" label="Charged to clients" />
        <Legend swatch="#2a2210" label="Atlas cost" />
        <Legend swatch="#f3e0a4" label="Margin" line />
      </div>
    </div>
  );
}

function Legend({
  swatch,
  label,
  line = false,
}: {
  swatch: string;
  label: string;
  line?: boolean;
}) {
  return (
    <span className="flex items-center gap-2">
      <span
        className={line ? "h-[2px] w-4 rounded-full" : "h-2.5 w-2.5 rounded-[3px]"}
        style={{ background: swatch }}
      />
      {label}
    </span>
  );
}
