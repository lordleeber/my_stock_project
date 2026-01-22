"use client";

import { useState, useEffect } from "react";

interface StockData {
  date: string;
  symbol: string;
  name: string;
  close: number;
  volume: number;
  change?: number | null;
  ma5?: number;
  ma10?: number;
  ma20?: number;
  ma60?: number;
  vma5?: number;
  vma10?: number;
  vma20?: number;
  vma60?: number;
  vma120?: number;
  vma240?: number;
  [key: string]: any; // 允許動態存取以進行除錯
}

type Category = "volume" | "ma" | "vma" | "breakout";
type SortOrder = "asc" | "desc";

export default function Home() {
  const [selectedDate, setSelectedDate] = useState("");
  const [category, setCategory] = useState<Category>("volume");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [stocks, setStocks] = useState<StockData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Backtest State
  const [activeTab, setActiveTab] = useState<"dashboard" | "backtest">("dashboard");
  const [btStartDate, setBtStartDate] = useState("2025-05-01");
  const [btEndDate, setBtEndDate] = useState("2025-05-31");
  const [btMode, setBtMode] = useState<"shares" | "amount">("shares");
  const [btCapital, setBtCapital] = useState(100000);
  const [btHoldDays, setBtHoldDays] = useState(3);
  const [btPyramiding, setBtPyramiding] = useState(true);
  const [btOnlyRedCandle, setBtOnlyRedCandle] = useState(false);
  const [btTakeProfit, setBtTakeProfit] = useState<number>(0);
  const [btStopLoss, setBtStopLoss] = useState<number>(0);
  const [btResult, setBtResult] = useState<any>(null);
  const [btLoading, setBtLoading] = useState(false);

  // ... (useEffect and fetchData unchanged) ...

  const runBacktest = async () => {
    setBtLoading(true);
    setBtResult(null);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/backtest/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_date: btStartDate,
          end_date: btEndDate,
          strategy_mode: btMode,
          capital: btCapital,
          hold_days: btHoldDays,
          allow_pyramiding: btPyramiding,
          only_red_candle: btOnlyRedCandle,
          take_profit_pct: btTakeProfit ? btTakeProfit / 100 : null,
          stop_loss_pct: btStopLoss ? btStopLoss / 100 : null
        })
      });
      if (!res.ok) throw new Error("回測執行失敗");
      const data = await res.json();
      setBtResult(data);
    } catch (err) {
      console.error(err);
      alert("回測執行失敗，請檢查後端日誌");
    } finally {
      setBtLoading(false);
    }
  };

  // ... (helper functions) ...

  return (
    // ... (Container and Tabs) ...
        // ... (Dashboard View) ...
        ) : (
          <div className="p-4">
            <div className="bg-gray-50 p-6 rounded-lg mb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-bold mb-1">開始日期</label>
                <input type="date" value={btStartDate} onChange={(e)=>setBtStartDate(e.target.value)} className="w-full border p-2 rounded"/>
              </div>
              <div>
                <label className="block text-sm font-bold mb-1">結束日期</label>
                <input type="date" value={btEndDate} onChange={(e)=>setBtEndDate(e.target.value)} className="w-full border p-2 rounded"/>
              </div>
              <div>
                <label className="block text-sm font-bold mb-1">持有天數</label>
                <input type="number" value={btHoldDays} onChange={(e)=>setBtHoldDays(Number(e.target.value))} className="w-full border p-2 rounded"/>
              </div>
              <div>
                <label className="block text-sm font-bold mb-1">策略模式</label>
                <select value={btMode} onChange={(e)=>setBtMode(e.target.value as any)} className="w-full border p-2 rounded">
                  <option value="shares">固定張數 (1張)</option>
                  <option value="amount">固定金額 (預設10萬)</option>
                </select>
              </div>
              {btMode === 'amount' && (
                <div>
                  <label className="block text-sm font-bold mb-1">初始資金</label>
                  <input type="number" value={btCapital} onChange={(e)=>setBtCapital(Number(e.target.value))} className="w-full border p-2 rounded"/>
                </div>
              )}
              
              {/* 停損停利設定 */}
              <div>
                <label className="block text-sm font-bold mb-1 text-green-600">停利 (%) <span className="text-xs font-normal text-gray-500">(選填)</span></label>
                <input 
                  type="number" 
                  placeholder="例如: 10" 
                  value={btTakeProfit ?? ""} 
                  onChange={(e)=>setBtTakeProfit(e.target.value ? Number(e.target.value) : null)} 
                  className="w-full border p-2 rounded"
                />
              </div>
              <div>
                <label className="block text-sm font-bold mb-1 text-red-600">停損 (%) <span className="text-xs font-normal text-gray-500">(選填)</span></label>
                <input 
                  type="number" 
                  placeholder="例如: 5" 
                  value={btStopLoss ?? ""} 
                  onChange={(e)=>setBtStopLoss(e.target.value ? Number(e.target.value) : null)} 
                  className="w-full border p-2 rounded"
                />
              </div>

              <div className="flex items-center space-x-4 md:col-span-3 mt-2">
                <div className="flex items-center">
                  <input 
                    id="pyramiding" 
                    type="checkbox" 
                    checked={btPyramiding} 
                    onChange={(e)=>setBtPyramiding(e.target.checked)} 
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <label htmlFor="pyramiding" className="ml-2 block text-sm font-bold text-gray-900">允許重複加碼 (Pyramiding)</label>
                </div>
                <div className="flex items-center">
                  <input 
                    id="onlyRedCandle" 
                    type="checkbox" 
                    checked={btOnlyRedCandle} 
                    onChange={(e)=>setBtOnlyRedCandle(e.target.checked)} 
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <label htmlFor="onlyRedCandle" className="ml-2 block text-sm font-bold text-red-600">只買紅K (Close &gt; Open)</label>
                </div>
              </div>
              <div className="flex items-end md:col-span-3 mt-4">
                <button onClick={runBacktest} disabled={btLoading} className="w-full bg-indigo-600 text-white px-6 py-2 rounded hover:bg-indigo-700 disabled:bg-gray-400">
                  {btLoading ? "回測中..." : "開始回測"}
                </button>
              </div>
            </div>