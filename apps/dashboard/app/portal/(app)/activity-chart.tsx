"use client";

import { useId, useMemo, useState } from "react";

/**
 * Thirty days of publishing activity.
 *
 * Hand-drawn SVG rather than a charting library: this is one small area chart
 * with a hover readout, and pulling in a chart package for it would ship far
 * more than it saves. The scale is computed once and every mark, gridline and
 * label is placed from it, so the axis always tells the truth about the shape.
 */
export type TimelinePoint = { date: string; published: number };

const WIDTH = 720;
const HEIGHT = 180;
const PADDING = { top: 12, right: 8, bottom: 22, left: 8 };

export function ActivityChart({ data }: { data: TimelinePoint[] }) {
  const gradientId = useId();
  const [hover, setHover] = useState<number | null>(null);

  const { points, areaPath, linePath, max, plotWidth, plotHeight } = useMemo(() => {
    const plotWidth = WIDTH - PADDING.left - PADDING.right;
    const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;
    // A flat-zero series still needs a scale, or every point lands on the axis
    // and the chart looks broken rather than empty.
    const max = Math.max(1, ...data.map((d) => d.published));

    const points = data.map((point, index) => ({
      ...point,
      x: PADDING.left + (index / Math.max(1, data.length - 1)) * plotWidth,
      y: PADDING.top + plotHeight - (point.published / max) * plotHeight,
    }));

    const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
    const areaPath =
      `${linePath} L${points[points.length - 1]?.x ?? PADDING.left},${PADDING.top + plotHeight}` +
      ` L${points[0]?.x ?? PADDING.left},${PADDING.top + plotHeight} Z`;

    return { points, areaPath, linePath, max, plotWidth, plotHeight };
  }, [data]);

  const total = data.reduce((sum, d) => sum + d.published, 0);
  const active = hover !== null ? points[hover] : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Pubblicazioni · ultimi 30 giorni
          </p>
          <p className="text-2xl font-semibold tabular-nums">{total}</p>
        </div>
        {active && (
          <p className="text-sm text-muted-foreground tabular-nums">
            {new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long" }).format(
              new Date(active.date)
            )}
            : <span className="font-medium text-foreground">{active.published}</span>
          </p>
        )}
      </div>

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-44 w-full min-w-[32rem]"
          role="img"
          aria-label={`Andamento pubblicazioni: ${total} negli ultimi 30 giorni`}
          onMouseLeave={() => setHover(null)}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.28" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Gridlines carry the scale: each one is a value the chart reaches. */}
          {[0, 0.5, 1].map((ratio) => {
            const y = PADDING.top + plotHeight - ratio * plotHeight;
            return (
              <g key={ratio}>
                <line
                  x1={PADDING.left}
                  x2={WIDTH - PADDING.right}
                  y1={y}
                  y2={y}
                  stroke="currentColor"
                  strokeOpacity="0.12"
                  strokeDasharray={ratio === 0 ? undefined : "3 4"}
                />
                <text
                  x={PADDING.left}
                  y={y - 4}
                  className="fill-muted-foreground text-[10px]"
                  fontSize="10"
                >
                  {Math.round(ratio * max)}
                </text>
              </g>
            );
          })}

          <g className="text-primary">
            <path d={areaPath} fill={`url(#${gradientId})`} />
            <path
              d={linePath}
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
              className="[stroke-dasharray:1400] [stroke-dashoffset:0] motion-safe:animate-[dash_1.1s_ease-out]"
            />
            {active && (
              <>
                <line
                  x1={active.x}
                  x2={active.x}
                  y1={PADDING.top}
                  y2={PADDING.top + plotHeight}
                  stroke="currentColor"
                  strokeOpacity="0.35"
                />
                <circle cx={active.x} cy={active.y} r="4" fill="currentColor" />
              </>
            )}
          </g>

          {/* Invisible hit areas: one per day, full height, so hovering anywhere
              in a column reads that day rather than requiring the exact point. */}
          {points.map((point, index) => (
            <rect
              key={point.date}
              x={point.x - plotWidth / data.length / 2}
              y={PADDING.top}
              width={plotWidth / data.length}
              height={plotHeight}
              fill="transparent"
              onMouseEnter={() => setHover(index)}
            />
          ))}

          <text x={PADDING.left} y={HEIGHT - 6} className="fill-muted-foreground" fontSize="10">
            {new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short" }).format(
              new Date(data[0]?.date ?? Date.now())
            )}
          </text>
          <text
            x={WIDTH - PADDING.right}
            y={HEIGHT - 6}
            textAnchor="end"
            className="fill-muted-foreground"
            fontSize="10"
          >
            oggi
          </text>
        </svg>
      </div>

      <style>{`@keyframes dash { from { stroke-dashoffset: 1400 } to { stroke-dashoffset: 0 } }`}</style>
    </div>
  );
}
