"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { usdPrecise } from "@/lib/format";

/**
 * Grafy dashboardu — monochróm podľa referencie. Žiadne farebné série: bary
 * majú vertikálny gradient biela→priehľadná, čiary sa líšia jasom a čiarkou.
 */

const AXIS = { fill: "#52525b", fontSize: 11 };
const GRID = "#1a1a1a";

/** Odtiene pre stepped line — poradie určuje, ktorá séria dostane ktorý. */
const LINE_STROKE = ["#fafafa", "#a1a1aa", "#71717a", "#52525b"];
const LINE_DASH: (string | undefined)[] = [undefined, undefined, "4 3", "2 3"];

export type SpendPoint = { label: string; value: number };

/** Denná útrata — bar chart s vertikálnym gradientom. */
export function SpendChart({ data }: { data: SpendPoint[] }) {
  const empty = data.every((point) => point.value === 0);

  return (
    <div className="px-2 pb-4 pt-5">
      <ResponsiveContainer width="100%" height={196}>
        <BarChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id="app-bar-mono" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ffffff" stopOpacity={0.92} />
              <stop offset="100%" stopColor="#ffffff" stopOpacity={0.12} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis
            dataKey="label"
            tick={AXIS}
            tickLine={false}
            axisLine={{ stroke: GRID }}
            tickMargin={8}
          />
          <YAxis
            tick={AXIS}
            tickLine={false}
            axisLine={false}
            width={52}
            tickFormatter={(value: number) => usdPrecise(value)}
          />
          <Tooltip
            cursor={{ fill: "rgba(255,255,255,0.04)" }}
            content={<MonoTooltip format={usdPrecise} />}
          />
          <Bar
            dataKey="value"
            fill="url(#app-bar-mono)"
            radius={[3, 3, 0, 0]}
            maxBarSize={34}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
      {empty && (
        <p className="px-3 pt-2 text-[11.5px] text-[var(--app-text-4)]">
          Nothing charged in this window yet.
        </p>
      )}
    </div>
  );
}

export type SeriesPoint = { label: string } & Record<string, string | number>;

/** Správy po modelkách — stepped line, série rozlíšené jasom a čiarkou. */
export function MessagesChart({
  data,
  series,
}: {
  data: SeriesPoint[];
  series: { key: string; label: string }[];
}) {
  return (
    <div className="px-2 pb-4 pt-5">
      <ResponsiveContainer width="100%" height={196}>
        <LineChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: 4 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis
            dataKey="label"
            tick={AXIS}
            tickLine={false}
            axisLine={{ stroke: GRID }}
            tickMargin={8}
          />
          <YAxis
            tick={AXIS}
            tickLine={false}
            axisLine={false}
            width={36}
            allowDecimals={false}
          />
          <Tooltip cursor={{ stroke: "#2e2e2e" }} content={<MonoTooltip />} />
          {series.map((item, index) => (
            <Line
              key={item.key}
              type="step"
              dataKey={item.key}
              name={item.label}
              stroke={LINE_STROKE[index % LINE_STROKE.length]}
              strokeDasharray={LINE_DASH[index % LINE_DASH.length]}
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0 }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>

      {/* Legenda je textová — presne ako referencia. */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 px-3 pt-3">
        {series.map((item, index) => (
          <span
            key={item.key}
            className="flex items-center gap-2 text-[11.5px] text-[var(--app-text-3)]"
          >
            <span
              className="h-px w-4 shrink-0"
              style={{
                borderTop: `1.5px ${LINE_DASH[index % LINE_DASH.length] ? "dashed" : "solid"} ${
                  LINE_STROKE[index % LINE_STROKE.length]
                }`,
              }}
            />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}

type TooltipEntry = { name?: string | number; value?: string | number; color?: string };

/** Tooltip bez farieb knižnice — tmavý panel, biele hodnoty. */
function MonoTooltip({
  active,
  payload,
  label,
  format,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string | number;
  format?: (value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-[#2e2e2e] bg-[#0e0e0e] px-3 py-2 shadow-[0_12px_32px_rgba(0,0,0,0.7)]">
      <p className="text-[11px] text-[#71717a]">{label}</p>
      <ul className="mt-1 space-y-0.5">
        {payload.map((entry, index) => (
          <li
            key={`${entry.name}-${index}`}
            className="flex items-center gap-3 text-[12px] text-[#fafafa]"
          >
            <span className="text-[#a1a1aa]">{entry.name}</span>
            <span className="ml-auto tabular-nums">
              {format ? format(Number(entry.value ?? 0)) : entry.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
