import { usdPrecise } from "@/lib/format";
import type { DayBucket } from "@/lib/usage";

/**
 * Denná spotreba ako čisté SVG — žiadna grafová knižnica, žiaden client bundle.
 * Monochróm: bary majú vertikálny gradient biela→priehľadná, ako referencia.
 * Tooltip rieši natívny `<title>`.
 */
export function UsageChart({ days }: { days: DayBucket[] }) {
  const max = Math.max(...days.map((day) => day.total), 0.0001);
  const width = 100;
  const gap = 0.6;
  const barWidth = Math.max(0.6, width / days.length - gap);

  return (
    <div className="px-5 pb-5 pt-5">
      <svg
        viewBox={`0 0 ${width} 34`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Daily spend for the selected period"
        className="h-40 w-full overflow-visible"
      >
        <defs>
          <linearGradient id="usage-bar" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.92" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0.12" />
          </linearGradient>
        </defs>

        {[0.25, 0.5, 0.75, 1].map((line) => (
          <line
            key={line}
            x1={0}
            x2={width}
            y1={34 - line * 32}
            y2={34 - line * 32}
            stroke="#1a1a1a"
            strokeWidth={0.15}
          />
        ))}

        {days.map((day, index) => {
          const height = Math.max(day.total > 0 ? 0.6 : 0, (day.total / max) * 32);
          const x = index * (barWidth + gap);
          return (
            <g key={day.date}>
              <title>{`${day.label}: ${usdPrecise(day.total)}`}</title>
              <rect
                x={x}
                y={34 - height}
                width={barWidth}
                height={height}
                rx={0.3}
                fill="url(#usage-bar)"
                opacity={day.total > 0 ? 1 : 0.2}
              />
            </g>
          );
        })}
      </svg>

      <div className="mt-3 flex justify-between text-[11px] text-[var(--app-text-4)]">
        <span>{days[0]?.label}</span>
        <span>{days[Math.floor(days.length / 2)]?.label}</span>
        <span>{days[days.length - 1]?.label}</span>
      </div>
    </div>
  );
}
