"use client";

import { useState } from "react";
import CandlestickChart from "./components/CandlestickChart";
import InstitutionalChart from "./components/InstitutionalChart";

export default function Home() {
  // Tab State
  const [activeTab, setActiveTab] = useState<"dashboard" | "backtest" | "scanner">("dashboard");

  // Backtest State
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

  // Scanner State
  const [scanDate, setScanDate] = useState("");
  const [scanMinVolume, setScanMinVolume] = useState(5000000);
  const [scanVolumeRatio, setScanVolumeRatio] = useState(4.0);
  const [scanResults, setScanResults] = useState<any[]>([]);
  const [scanLoading, setScanLoading] = useState(false);
  const [chartDataCache, setChartDataCache] = useState<Record<string, any[]>>({});
  const [expandedCharts, setExpandedCharts] = useState<Set<string>>(new Set());
  const [institutionalDataCache, setInstitutionalDataCache] = useState<Record<string, any[]>>({});

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
          take_profit_pct: btTakeProfit ? btTakeProfit / 100 : 0,
          stop_loss_pct: btStopLoss ? btStopLoss / 100 : 0
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

  const runScanner = async () => {
    if (!scanDate) {
      alert("請選擇掃描日期");
      return;
    }

    setScanLoading(true);
    setScanResults([]);
    setExpandedCharts(new Set());
    setChartDataCache({});
    setInstitutionalDataCache({});

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const params = new URLSearchParams({
        date: scanDate,
        min_volume: scanMinVolume.toString(),
        volume_ratio: scanVolumeRatio.toString(),
      });

      const res = await fetch(`${apiUrl}/scanner/volume-spike?${params}`);
      if (!res.ok) throw new Error("掃描失敗");

      const data = await res.json();
      setScanResults(data);

      // Pre-load chart data for all results
      if (data.length > 0) {
        const chartPromises = data.map((stock: any) =>
          fetchChartData(stock.symbol, stock.date)
        );
        await Promise.all(chartPromises);

        const initialExpanded = new Set(data.map((s: any) => s.symbol)) as Set<string>;
        setExpandedCharts(initialExpanded);
      }
    } catch (err) {
      console.error(err);
      alert("掃描失敗，請檢查後端服務");
    } finally {
      setScanLoading(false);
    }
  };

  const fetchChartData = async (symbol: string, date: string) => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const [candleRes, instRes] = await Promise.all([
        fetch(`${apiUrl}/scanner/candlestick/${symbol}?date=${date}&days_before=90&days_after=90`),
        fetch(`${apiUrl}/scanner/institutional/${symbol}?date=${date}&days_before=90&days_after=90`),
      ]);

      if (candleRes.ok) {
        const candleData = await candleRes.json();
        setChartDataCache((prev) => ({ ...prev, [symbol]: candleData }));
      }
      if (instRes.ok) {
        const instData = await instRes.json();
        setInstitutionalDataCache((prev) => ({ ...prev, [symbol]: instData }));
      }
    } catch (err) {
      console.error(`Failed to load chart for ${symbol}:`, err);
    }
  };

  const toggleChart = async (symbol: string, date: string) => {
    const newExpanded = new Set(expandedCharts);

    if (expandedCharts.has(symbol)) {
      newExpanded.delete(symbol);
    } else {
      newExpanded.add(symbol);
      if (!chartDataCache[symbol]) {
        await fetchChartData(symbol, date);
      }
    }

    setExpandedCharts(newExpanded);
  };

  return (
    <div className="min-h-screen bg-gray-100">
      <div className="container mx-auto p-4">
        <h1 className="text-3xl font-bold mb-6">台股分析系統</h1>

        {/* Tabs */}
        <div className="flex border-b mb-6">
          <button
            onClick={() => setActiveTab("dashboard")}
            className={`px-6 py-2 font-bold ${
              activeTab === "dashboard"
                ? "border-b-2 border-blue-600 text-blue-600"
                : "text-gray-600"
            }`}
          >
            Dashboard
          </button>
          <button
            onClick={() => setActiveTab("backtest")}
            className={`px-6 py-2 font-bold ${
              activeTab === "backtest"
                ? "border-b-2 border-blue-600 text-blue-600"
                : "text-gray-600"
            }`}
          >
            策略回測
          </button>
          <button
            onClick={() => setActiveTab("scanner")}
            className={`px-6 py-2 font-bold ${
              activeTab === "scanner"
                ? "border-b-2 border-blue-600 text-blue-600"
                : "text-gray-600"
            }`}
          >
            爆量掃描器
          </button>
        </div>

        {/* Dashboard Tab */}
        {activeTab === "dashboard" && (
          <div className="p-4 bg-white rounded-lg shadow">
            <h2 className="text-xl font-bold mb-4">Dashboard</h2>
            <p className="text-gray-600">即將推出更多功能...</p>
          </div>
        )}

        {/* Backtest Tab */}
        {activeTab === "backtest" && (
          <div className="p-4">
            <div className="bg-gray-50 p-6 rounded-lg mb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-bold mb-1">開始日期</label>
                <input
                  type="date"
                  value={btStartDate}
                  onChange={(e) => setBtStartDate(e.target.value)}
                  className="w-full border p-2 rounded"
                />
              </div>
              <div>
                <label className="block text-sm font-bold mb-1">結束日期</label>
                <input
                  type="date"
                  value={btEndDate}
                  onChange={(e) => setBtEndDate(e.target.value)}
                  className="w-full border p-2 rounded"
                />
              </div>
              <div>
                <label className="block text-sm font-bold mb-1">持有天數</label>
                <input
                  type="number"
                  value={btHoldDays}
                  onChange={(e) => setBtHoldDays(Number(e.target.value))}
                  className="w-full border p-2 rounded"
                />
              </div>
              <div>
                <label className="block text-sm font-bold mb-1">策略模式</label>
                <select
                  value={btMode}
                  onChange={(e) => setBtMode(e.target.value as any)}
                  className="w-full border p-2 rounded"
                >
                  <option value="shares">固定張數 (1張)</option>
                  <option value="amount">固定金額 (預設10萬)</option>
                </select>
              </div>
              {btMode === "amount" && (
                <div>
                  <label className="block text-sm font-bold mb-1">初始資金</label>
                  <input
                    type="number"
                    value={btCapital}
                    onChange={(e) => setBtCapital(Number(e.target.value))}
                    className="w-full border p-2 rounded"
                  />
                </div>
              )}
              <div>
                <label className="block text-sm font-bold mb-1 text-green-600">
                  停利 (%) <span className="text-xs font-normal text-gray-500">(選填)</span>
                </label>
                <input
                  type="number"
                  placeholder="例如: 10"
                  value={btTakeProfit || ""}
                  onChange={(e) => setBtTakeProfit(e.target.value ? Number(e.target.value) : 0)}
                  className="w-full border p-2 rounded"
                />
              </div>
              <div>
                <label className="block text-sm font-bold mb-1 text-red-600">
                  停損 (%) <span className="text-xs font-normal text-gray-500">(選填)</span>
                </label>
                <input
                  type="number"
                  placeholder="例如: 5"
                  value={btStopLoss || ""}
                  onChange={(e) => setBtStopLoss(e.target.value ? Number(e.target.value) : 0)}
                  className="w-full border p-2 rounded"
                />
              </div>
              <div className="flex items-center space-x-4 md:col-span-3 mt-2">
                <div className="flex items-center">
                  <input
                    id="pyramiding"
                    type="checkbox"
                    checked={btPyramiding}
                    onChange={(e) => setBtPyramiding(e.target.checked)}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <label htmlFor="pyramiding" className="ml-2 block text-sm font-bold text-gray-900">
                    允許重複加碼 (Pyramiding)
                  </label>
                </div>
                <div className="flex items-center">
                  <input
                    id="onlyRedCandle"
                    type="checkbox"
                    checked={btOnlyRedCandle}
                    onChange={(e) => setBtOnlyRedCandle(e.target.checked)}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <label htmlFor="onlyRedCandle" className="ml-2 block text-sm font-bold text-red-600">
                    只買紅K (Close &gt; Open)
                  </label>
                </div>
              </div>
              <div className="flex items-end md:col-span-3 mt-4">
                <button
                  onClick={runBacktest}
                  disabled={btLoading}
                  className="w-full bg-indigo-600 text-white px-6 py-2 rounded hover:bg-indigo-700 disabled:bg-gray-400"
                >
                  {btLoading ? "回測中..." : "開始回測"}
                </button>
              </div>
            </div>

            {/* Backtest Results */}
            {btResult && (
              <div className="bg-white p-6 rounded-lg shadow">
                <h3 className="text-lg font-bold mb-4">回測結果</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                  <div>
                    <div className="text-sm text-gray-600">總交易次數</div>
                    <div className="text-xl font-bold">{btResult.summary.total_trades}</div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">總損益</div>
                    <div className={`text-xl font-bold ${btResult.summary.total_profit >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {btResult.summary.total_profit.toLocaleString()} 元
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">投資報酬率</div>
                    <div className={`text-xl font-bold ${btResult.summary.roi >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {btResult.summary.roi.toFixed(2)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">勝率</div>
                    <div className="text-xl font-bold">{btResult.summary.win_rate.toFixed(2)}%</div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">平均報酬</div>
                    <div className="text-xl font-bold">{btResult.summary.avg_return.toFixed(2)}%</div>
                  </div>
                </div>
                <div className="mt-4">
                  <h4 className="font-bold mb-2">交易明細 (顯示前10筆)</h4>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left p-2">代號</th>
                          <th className="text-left p-2">名稱</th>
                          <th className="text-left p-2">買入日期</th>
                          <th className="text-left p-2">賣出日期</th>
                          <th className="text-right p-2">買入價</th>
                          <th className="text-right p-2">賣出價</th>
                          <th className="text-right p-2">損益</th>
                          <th className="text-right p-2">報酬率</th>
                        </tr>
                      </thead>
                      <tbody>
                        {btResult.trades.slice(0, 10).map((trade: any, idx: number) => (
                          <tr key={idx} className="border-b">
                            <td className="p-2">{trade.symbol}</td>
                            <td className="p-2">{trade.name}</td>
                            <td className="p-2">{trade.buy_date}</td>
                            <td className="p-2">{trade.sell_date}</td>
                            <td className="text-right p-2">{trade.buy_price.toFixed(2)}</td>
                            <td className="text-right p-2">{trade.sell_price.toFixed(2)}</td>
                            <td className={`text-right p-2 ${trade.profit >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                              {trade.profit.toLocaleString()}
                            </td>
                            <td className={`text-right p-2 ${trade.return_rate >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                              {trade.return_rate.toFixed(2)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Scanner Tab */}
        {activeTab === "scanner" && (
          <div className="p-4">
            {/* Scanner Controls */}
            <div className="bg-gray-50 p-6 rounded-lg mb-6">
              <h2 className="text-xl font-bold mb-4">爆量掃描器設定</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-bold mb-1">掃描日期</label>
                  <input
                    type="date"
                    value={scanDate}
                    onChange={(e) => setScanDate(e.target.value)}
                    className="w-full border p-2 rounded"
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold mb-1">最小成交量 (張)</label>
                  <input
                    type="number"
                    value={scanMinVolume / 1000}
                    onChange={(e) => setScanMinVolume(Number(e.target.value) * 1000)}
                    className="w-full border p-2 rounded"
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold mb-1">爆量倍數</label>
                  <input
                    type="number"
                    step="0.1"
                    value={scanVolumeRatio}
                    onChange={(e) => setScanVolumeRatio(Number(e.target.value))}
                    className="w-full border p-2 rounded"
                  />
                </div>
              </div>
              <button
                onClick={runScanner}
                disabled={scanLoading}
                className="mt-4 w-full bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:bg-gray-400"
              >
                {scanLoading ? "掃描中..." : "開始掃描"}
              </button>
            </div>

            {/* Results */}
            {scanResults.length > 0 && (
              <div>
                <h3 className="text-lg font-bold mb-3">
                  掃描結果 ({scanResults.length} 支股票)
                </h3>
                <div className="space-y-4">
                  {scanResults.map((stock) => (
                    <div key={stock.symbol} className="border rounded-lg p-4 bg-white">
                      {/* Stock Info Row */}
                      <div className="flex justify-between items-center mb-2">
                        <div className="flex gap-4 items-center flex-wrap">
                          <span className="text-lg font-bold">
                            {stock.symbol} {stock.name}
                          </span>
                          <span className="text-sm text-gray-600">
                            開: {stock.open.toFixed(2)} 高: {stock.high.toFixed(2)} 低: {stock.low.toFixed(2)} 收: {stock.close.toFixed(2)}
                          </span>
                          <span className="text-sm text-gray-600">
                            成交量: {(stock.volume / 1000).toLocaleString()} 張
                          </span>
                          <span className="text-sm font-bold text-red-600">
                            量比: {stock.volume_ratio.toFixed(2)}x
                          </span>
                        </div>
                        <button
                          onClick={() => toggleChart(stock.symbol, stock.date)}
                          className="px-4 py-1 text-sm bg-gray-100 hover:bg-gray-200 rounded"
                        >
                          {expandedCharts.has(stock.symbol) ? "隱藏圖表" : "顯示圖表"}
                        </button>
                      </div>

                      {/* Chart */}
                      {expandedCharts.has(stock.symbol) && (
                        <div className="mt-4">
                          {chartDataCache[stock.symbol] ? (
                            <>
                              <CandlestickChart
                                data={chartDataCache[stock.symbol]}
                                symbol={stock.symbol}
                                name={stock.name}
                                scanDate={stock.date}
                              />
                              {institutionalDataCache[stock.symbol] && institutionalDataCache[stock.symbol].length > 0 && (
                                <div className="mt-4">
                                  <InstitutionalChart
                                    data={institutionalDataCache[stock.symbol]}
                                    scanDate={stock.date}
                                  />
                                </div>
                              )}
                            </>
                          ) : (
                            <div className="h-40 flex items-center justify-center text-gray-500">
                              載入圖表中...
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {scanResults.length === 0 && !scanLoading && (
              <div className="text-center text-gray-500 py-12">
                請選擇日期並點擊「開始掃描」
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
