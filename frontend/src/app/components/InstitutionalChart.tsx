"use client";

import { useEffect, useRef } from "react";
import { createChart, HistogramSeries, LineSeries } from "lightweight-charts";

interface InstitutionalData {
  date: string;
  foreign_net: number;
  trust_net: number;
  foreign_held_shares?: number;
  trust_held_shares?: number;
}

interface InstitutionalChartProps {
  data: InstitutionalData[];
  scanDate: string;
}

function createInstitutionalSubChart(
  container: HTMLDivElement,
  data: InstitutionalData[],
  field: "foreign_net" | "trust_net",
  heldField: "foreign_held_shares" | "trust_held_shares",
  scanDate: string
) {
  const hasHeldData = data.some((d) => d[heldField] != null);
  const chart = createChart(container, {
    width: container.clientWidth,
    height: 200,
    layout: {
      background: { color: "#ffffff" },
      textColor: "#333",
    },
    grid: {
      vertLines: { color: "#f0f0f0" },
      horzLines: { visible: false, color: "transparent" },
    },
    leftPriceScale: {
      visible: true,
      drawTicks: false,
    },
    rightPriceScale: {
      visible: hasHeldData,
      drawTicks: false,
    },
    handleScroll: {
      mouseWheel: false,
    },
    handleScale: {
      mouseWheel: false,
    },
    timeScale: {
      timeVisible: true,
      secondsVisible: false,
    },
  });

  // Main histogram series
  const series = chart.addSeries(HistogramSeries, {
    priceScaleId: "left",
    priceFormat: {
      type: "volume",
    },
    lastValueVisible: false,
    priceLineVisible: false,
  });

  const chartData = data.map((d) => {
    const value = d[field] / 1000; // convert to 張
    return {
      time: d.date as any,
      value,
      color: value >= 0 ? "#ef444480" : "#22c55e80",
    };
  });

  series.setData(chartData);

  // Add held shares line on right axis
  if (hasHeldData) {
    const heldData = data
      .filter((d) => d[heldField] != null)
      .map((d) => ({
        time: d.date as any,
        value: d[heldField]! / 1000, // convert to 張
      }));

    if (heldData.length > 0) {
      const heldSeries = chart.addSeries(LineSeries, {
        color: "#f59e0b",
        lineWidth: 2,
        priceScaleId: "right",
        lastValueVisible: true,
        priceLineVisible: false,
        priceFormat: {
          type: "volume",
        },
      });
      heldSeries.setData(heldData);
    }
  }

  // Highlight scan date
  const highlightSeries = chart.addSeries(HistogramSeries, {
    priceScaleId: "highlight",
    lastValueVisible: false,
    priceLineVisible: false,
  });
  chart.priceScale("highlight").applyOptions({
    visible: false,
    scaleMargins: { top: 0, bottom: 0 },
  });
  const maxVal = Math.max(...data.map((d) => Math.abs(d[field] / 1000)), 1);
  highlightSeries.setData(
    chartData.map((d) => ({
      time: d.time,
      value: d.time === scanDate ? maxVal * 4 : 0,
      color: d.time === scanDate ? "#facc1580" : "transparent",
    }))
  );

  // Center on scan date ±60 bars
  const scanIndex = chartData.findIndex((d) => d.time === scanDate);
  if (scanIndex >= 0) {
    chart.timeScale().setVisibleLogicalRange({
      from: scanIndex - 60,
      to: scanIndex + 60,
    });
  }

  // Resize handler
  const handleResize = () => {
    chart.resize(container.clientWidth, 200);
  };
  window.addEventListener("resize", handleResize);

  return () => {
    window.removeEventListener("resize", handleResize);
    chart.remove();
  };
}

export default function InstitutionalChart({
  data,
  scanDate,
}: InstitutionalChartProps) {
  const foreignRef = useRef<HTMLDivElement>(null);
  const trustRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!foreignRef.current || !trustRef.current || data.length === 0) return;

    const cleanupForeign = createInstitutionalSubChart(
      foreignRef.current,
      data,
      "foreign_net",
      "foreign_held_shares",
      scanDate
    );

    const cleanupTrust = createInstitutionalSubChart(
      trustRef.current,
      data,
      "trust_net",
      "trust_held_shares",
      scanDate
    );

    return () => {
      cleanupForeign();
      cleanupTrust();
    };
  }, [data, scanDate]);

  const hasForeignHeld = data.some((d) => d.foreign_held_shares != null);
  const hasTrustHeld = data.some((d) => d.trust_held_shares != null);

  return (
    <div className="w-full space-y-2">
      <div>
        <div className="text-sm font-semibold text-gray-700">
          外資買賣超
          {hasForeignHeld && (
            <span className="ml-2 text-xs font-normal text-amber-500">● 外資總持股(張) → 右軸</span>
          )}
        </div>
        <div className="relative w-full border rounded">
          <div ref={foreignRef} className="w-full" />
          <span className="absolute left-1 text-[10px] text-gray-400" style={{ bottom: "4px" }}>
            買賣超(張)
          </span>
        </div>
      </div>
      <div>
        <div className="text-sm font-semibold text-gray-700">
          投信買賣超
          {hasTrustHeld && (
            <span className="ml-2 text-xs font-normal text-amber-500">● 投信總持股(張) → 右軸</span>
          )}
        </div>
        <div className="relative w-full border rounded">
          <div ref={trustRef} className="w-full" />
          <span className="absolute left-1 text-[10px] text-gray-400" style={{ bottom: "4px" }}>
            買賣超(張)
          </span>
        </div>
      </div>
    </div>
  );
}
