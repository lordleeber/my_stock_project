"use client";

import { useEffect, useRef } from "react";
import { createChart, CandlestickSeries, LineSeries, HistogramSeries } from "lightweight-charts";

interface CandlestickData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ma5?: number;
  ma10?: number;
  ma20?: number;
  ma60?: number;
}

interface CandlestickChartProps {
  data: CandlestickData[];
  symbol: string;
  name: string;
  scanDate: string;
}

export default function CandlestickChart({
  data,
  symbol,
  name,
  scanDate,
}: CandlestickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    if (!chartContainerRef.current || data.length === 0) return;

    // Create chart
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 400,
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

    chartRef.current = chart;

    // Add candlestick series
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#ef4444", // Red for up (Taiwan convention)
      downColor: "#22c55e", // Green for down
      borderUpColor: "#ef4444",
      borderDownColor: "#22c55e",
      wickUpColor: "#ef4444",
      wickDownColor: "#22c55e",
    });

    // Transform data
    const candleData = data.map((d) => ({
      time: d.date,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    candlestickSeries.setData(candleData);

    // Add MA lines
    if (data.some((d) => d.ma5)) {
      const ma5Series = chart.addSeries(LineSeries, { color: "#f97316", lineWidth: 1, lastValueVisible: false, priceLineVisible: false });
      ma5Series.setData(
        data
          .filter((d) => d.ma5 !== null && d.ma5 !== undefined)
          .map((d) => ({ time: d.date, value: d.ma5! }))
      );
    }

    if (data.some((d) => d.ma10)) {
      const ma10Series = chart.addSeries(LineSeries, { color: "#3b82f6", lineWidth: 1, lastValueVisible: false, priceLineVisible: false });
      ma10Series.setData(
        data
          .filter((d) => d.ma10 !== null && d.ma10 !== undefined)
          .map((d) => ({ time: d.date, value: d.ma10! }))
      );
    }

    if (data.some((d) => d.ma20)) {
      const ma20Series = chart.addSeries(LineSeries, { color: "#ef4444", lineWidth: 1, lastValueVisible: false, priceLineVisible: false });
      ma20Series.setData(
        data
          .filter((d) => d.ma20 !== null && d.ma20 !== undefined)
          .map((d) => ({ time: d.date, value: d.ma20! }))
      );
    }

    if (data.some((d) => d.ma60)) {
      const ma60Series = chart.addSeries(LineSeries, { color: "#a855f7", lineWidth: 1, lastValueVisible: false, priceLineVisible: false });
      ma60Series.setData(
        data
          .filter((d) => d.ma60 !== null && d.ma60 !== undefined)
          .map((d) => ({ time: d.date, value: d.ma60! }))
      );
    }

    // Add volume histogram
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: "#cbd5e1",
      priceFormat: {
        type: "volume",
      },
      priceScaleId: "left",
    });

    chart.priceScale("left").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const volumeData = data.map((d) => ({
      time: d.date,
      value: d.volume / 1000,
      color: d.close >= d.open ? "#ef444480" : "#22c55e80",
    }));

    volumeSeries.setData(volumeData);

    // Highlight scan date background with yellow
    const highlightSeries = chart.addSeries(HistogramSeries, {
      color: "#facc1580",
      priceScaleId: "highlight",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("highlight").applyOptions({
      visible: false,
      scaleMargins: { top: 0, bottom: 0 },
    });
    const maxPrice = Math.max(...data.map((d) => d.high));
    highlightSeries.setData(
      candleData.map((d) => ({
        time: d.time,
        value: d.time === scanDate ? maxPrice * 2 : 0,
        color: d.time === scanDate ? "#facc1580" : "transparent",
      }))
    );

    // Set visible range: center on scanDate with ±60 bars of space
    const scanIndex = candleData.findIndex((d) => d.time === scanDate);
    if (scanIndex >= 0) {
      chart.timeScale().setVisibleLogicalRange({
        from: scanIndex - 60,
        to: scanIndex + 60,
      });
    }

    // Resize handler
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.resize(
          chartContainerRef.current.clientWidth,
          400
        );
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [data, scanDate]);

  return (
    <div className="w-full">
      <div className="text-sm font-semibold mb-2 text-gray-700">
        {symbol} {name} - K線圖
      </div>
      <div className="relative w-full border rounded">
        <div ref={chartContainerRef} className="w-full" />
        <span className="absolute left-1 text-[10px] text-gray-400" style={{ bottom: "4px" }}>
          成交量(張)
        </span>
      </div>
      <div className="flex gap-4 text-xs text-gray-600 mt-2">
        <span className="flex items-center gap-1">
          <span className="w-3 h-0.5 bg-orange-500"></span> MA5
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-0.5 bg-blue-500"></span> MA10
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-0.5 bg-red-500"></span> MA20
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-0.5 bg-purple-500"></span> MA60
        </span>
      </div>
    </div>
  );
}
