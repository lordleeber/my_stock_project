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
  const [btResult, setBtResult] = useState<any>(null);
  const [btLoading, setBtLoading] = useState(false);

  useEffect(() => {
    // 取得當地時間 (解決 UTC 問題)
    const now = new Date();
    const offset = now.getTimezoneOffset(); 
    const localDate = new Date(now.getTime() - (offset*60*1000));
    setSelectedDate(localDate.toISOString().split("T")[0]);
  }, []);

  useEffect(() => {
    setSortOrder("desc");
  }, [category]);

  const fetchData = async () => {
    if (!selectedDate) return;
    setLoading(true);
    setError(null);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const dateParam = selectedDate.replace(/-/g, "");
      let endpoint = `/quotes/top-volume?date=${dateParam}&limit=10&sort=${sortOrder}`;
      
      if (category === "ma") endpoint = `/analysis/ma?date=${dateParam}&limit=10&sort=${sortOrder}`;
      else if (category === "vma") endpoint = `/analysis/vma?date=${dateParam}&limit=10&sort=${sortOrder}`;
      else if (category === "breakout") endpoint = `/analysis/volume-breakout?date=${dateParam}&limit=20&multiplier=5`;

      console.log(`Fetching: ${apiUrl}${endpoint}`);
      
      const response = await fetch(`${apiUrl}${endpoint}`, { cache: 'no-store' });
      
      if (!response.ok) throw new Error("無法取得資料");
      
      const data = await response.json();
      console.log("API Response Data:", data); 
      setStocks(data);
      if (data.length === 0) setError("該日期無符合條件的資料。");
    } catch (err) {
      console.error(err);
      setError("發生錯誤");
    } finally {
      setLoading(false);
    }
  };

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
          allow_pyramiding: btPyramiding
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

  // 安全格式化數值
  const safeFixed = (val: any) => {
    const num = Number(val);
    if (isNaN(num) || val === null || val === undefined) return "-";
    return num.toFixed(2);
  };

  // 安全格式化成交量 (除以 1000)
  const safeVol = (val: any) => {
    const num = Number(val);
    if (isNaN(num) || val === null || val === undefined) return "-";
    return Math.round(num / 1000).toLocaleString();
  };

  return (
    <div className="min-h-screen bg-gray-100 p-8">
      <div className="max-w-6xl mx-auto bg-white rounded-xl shadow p-6">
        <h1 className="text-2xl font-bold mb-6 text-center">台股分析儀表板</h1>
        
        {/* Tabs */}
        <div className="flex justify-center mb-6 border-b">
          <button 
            className={`px-6 py-2 ${activeTab === 'dashboard' ? 'border-b-2 border-blue-600 text-blue-600 font-bold' : 'text-gray-500'}`}
            onClick={() => setActiveTab('dashboard')}
          >
            每日行情看板
          </button>
          <button 
            className={`px-6 py-2 ${activeTab === 'backtest' ? 'border-b-2 border-blue-600 text-blue-600 font-bold' : 'text-gray-500'}`}
            onClick={() => setActiveTab('backtest')}
          >
            策略回測實驗室
          </button>
        </div>

        {activeTab === 'dashboard' ? (
          <>
        <div className="flex flex-wrap gap-4 mb-8 items-end bg-gray-50 p-4 rounded-lg">
          <div>
            <label className="block text-sm mb-1">日期</label>
            <input type="date" value={selectedDate} onChange={(e)=>setSelectedDate(e.target.value)} className="border p-2 rounded"/>
          </div>
          <div>
            <label className="block text-sm mb-1">指標</label>
            <select value={category} onChange={(e)=>setCategory(e.target.value as Category)} className="border p-2 rounded">
              <option value="volume">成交量排行榜</option>
              <option value="ma">價格均線 (MA)</option>
              <option value="vma">成交量均線 (VMA)</option>
              <option value="breakout">量能爆發 (Vol &gt; 5x VMA10)</option>
            </select>
          </div>
          <div>
            <label className="block text-sm mb-1">排序</label>
            <select value={sortOrder} onChange={(e)=>setSortOrder(e.target.value as SortOrder)} className="border p-2 rounded" disabled={category === "breakout"}>
              <option value="desc">遞減</option>
              <option value="asc">遞增</option>
            </select>
          </div>
          <button onClick={fetchData} className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700">查詢</button>
        </div>

        {error && <div className="text-red-500 mb-4">{error}</div>}

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-gray-200">
                <th className="p-3 border">代號</th>
                <th className="p-3 border">名稱</th>
                <th className="p-3 border text-right">收盤</th>
                {/* 成交量常駐顯示 */}
                <th className="p-3 border text-right">成交量(張)</th>
                
                {category === "volume" && <th className="p-3 border text-right">漲跌</th>}
                
                {category === "ma" && (
                  <>
                    <th className="p-3 border text-right text-blue-600">MA5</th>
                    <th className="p-3 border text-right text-orange-600">MA20</th>
                    <th className="p-3 border text-right text-purple-600">MA60</th>
                  </>
                )}
                {category === "vma" && (
                  <>
                    <th className="p-3 border text-right text-blue-600">VMA5(張)</th>
                    <th className="p-3 border text-right text-orange-600">VMA20(張)</th>
                    <th className="p-3 border text-right text-purple-600">VMA60(張)</th>
                  </>
                )}
                {category === "breakout" && (
                  <>
                    <th className="p-3 border text-right text-red-600">VMA10(張)</th>
                    <th className="p-3 border text-right text-red-600">爆發倍數</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {stocks.map((s) => (
                <tr key={s.symbol} className="hover:bg-gray-50">
                  <td className="p-3 border font-mono">{s.symbol}</td>
                  <td className="p-3 border">{s.name}</td>
                  <td className="p-3 border text-right font-bold">{safeFixed(s.close)}</td>
                  {/* 成交量常駐顯示 */}
                  <td className="p-3 border text-right">{safeVol(s.volume)}</td>
                  
                  {category === "volume" && (
                    <td className={`p-3 border text-right font-medium ${s.change && s.change > 0 ? "text-red-600" : s.change && s.change < 0 ? "text-green-600" : "text-gray-500"}`}>
                      {s.change && s.change > 0 ? `▲ ${s.change}` : s.change && s.change < 0 ? `▼ ${Math.abs(s.change)}` : "-"}
                    </td>
                  )}
                  
                  {category === "ma" && (
                    <>
                      <td className="p-3 border text-right">{safeFixed(s.ma5)}</td>
                      <td className="p-3 border text-right">{safeFixed(s.ma20)}</td>
                      <td className="p-3 border text-right">{safeFixed(s.ma60)}</td>
                    </>
                  )}
                  
                  {category === "vma" && (
                    <>
                      <td className="p-3 border text-right">{safeVol(s.vma5)}</td>
                      <td className="p-3 border text-right">{safeVol(s.vma20)}</td>
                      <td className="p-3 border text-right">{safeVol(s.vma60)}</td>
                    </>
                  )}

                  {category === "breakout" && (
                    <>
                      <td className="p-3 border text-right">{safeVol(s.vma10)}</td>
                      <td className="p-3 border text-right font-bold text-red-600">{safeFixed(s.ratio)} x</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
          </>
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
              <div className="flex items-end md:col-span-3">
                <button onClick={runBacktest} disabled={btLoading} className="w-full bg-indigo-600 text-white px-6 py-2 rounded hover:bg-indigo-700 disabled:bg-gray-400">
                  {btLoading ? "回測中..." : "開始回測"}
                </button>
              </div>
            </div>

            {btResult && (
              <div className="space-y-6">
                {/* Summary Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-blue-50 p-4 rounded text-center">
                    <div className="text-sm text-gray-500">總損益</div>
                    <div className={`text-xl font-bold ${btResult.summary.total_profit > 0 ? "text-red-600" : "text-green-600"}`}>
                      {btResult.summary.total_profit.toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-blue-50 p-4 rounded text-center">
                    <div className="text-sm text-gray-500">勝率</div>
                    <div className="text-xl font-bold">{btResult.summary.win_rate.toFixed(2)}%</div>
                  </div>
                  <div className="bg-blue-50 p-4 rounded text-center">
                    <div className="text-sm text-gray-500">ROI</div>
                    <div className="text-xl font-bold">{btResult.summary.roi.toFixed(2)}%</div>
                  </div>
                  <div className="bg-blue-50 p-4 rounded text-center">
                    <div className="text-sm text-gray-500">交易次數</div>
                    <div className="text-xl font-bold">{btResult.summary.total_trades}</div>
                  </div>
                </div>

                {/* Trade List */}
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm border-collapse">
                    <thead>
                      <tr className="bg-gray-200">
                        <th className="p-2 border">代號</th>
                        <th className="p-2 border">名稱</th>
                        <th className="p-2 border">買進日</th>
                        <th className="p-2 border">賣出日</th>
                        <th className="p-2 border text-right">股數</th>
                        <th className="p-2 border text-right">買入價</th>
                        <th className="p-2 border text-right">賣出價</th>
                        <th className="p-2 border text-right">損益</th>
                        <th className="p-2 border text-right">報酬率</th>
                      </tr>
                    </thead>
                    <tbody>
                      {btResult.trades.map((t: any, idx: number) => (
                        <tr key={idx} className="hover:bg-gray-50">
                          <td className="p-2 border">{t.symbol}</td>
                          <td className="p-2 border">{t.name}</td>
                          <td className="p-2 border">{t.buy_date}</td>
                          <td className="p-2 border">{t.sell_date}</td>
                          <td className="p-2 border text-right">{t.shares}</td>
                          <td className="p-2 border text-right">{t.buy_price}</td>
                          <td className="p-2 border text-right">{t.sell_price}</td>
                          <td className={`p-2 border text-right font-bold ${t.profit > 0 ? "text-red-600" : "text-green-600"}`}>
                            {t.profit.toLocaleString()}
                          </td>
                          <td className={`p-2 border text-right ${t.return_rate > 0 ? "text-red-600" : "text-green-600"}`}>
                            {t.return_rate.toFixed(2)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}