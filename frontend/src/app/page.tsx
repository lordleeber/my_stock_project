"use client";

import { useState, useEffect } from "react";

interface StockQuote {
  date: string;
  market: string;
  symbol: string;
  name: string;
  close: number;
  volume: number;
  change: number | null;
}

export default function Home() {
  const [selectedDate, setSelectedDate] = useState("");
  const [stocks, setStocks] = useState<StockQuote[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 初始化日期為今天
  useEffect(() => {
    const today = new Date().toISOString().split("T")[0];
    setSelectedDate(today);
  }, []);

  const fetchTopVolume = async () => {
    if (!selectedDate) return;

    setLoading(true);
    setError(null);
    try {
      // 注意：這裡使用 NEXT_PUBLIC_API_URL，若未設定則預設 localhost:8000
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${apiUrl}/quotes/top-volume?date=${selectedDate.replace(/-/g, "")}&limit=10`);
      
      if (!response.ok) {
        throw new Error("無法取得資料，請確認後端是否啟動或該日期是否有交易資料。");
      }
      
      const data = await response.json();
      setStocks(data);
      if (data.length === 0) {
        setError("該日期無成交資料。");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "發生未知錯誤");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white shadow-xl rounded-2xl p-8">
          <h1 className="text-3xl font-bold text-gray-900 text-center mb-8">
            台股成交量排行榜 (TOP 10)
          </h1>

          {/* 控制區 */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-10">
            <div className="flex items-center gap-3">
              <label htmlFor="date" className="text-gray-700 font-medium">選擇日期:</label>
              <input
                type="date"
                id="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="block w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 text-gray-900"
              />
            </div>
            <button
              onClick={fetchTopVolume}
              disabled={loading}
              className={`px-6 py-2 rounded-md font-semibold text-white shadow-md transition-all ${
                loading ? "bg-gray-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700 active:scale-95"
              }`}
            >
              {loading ? "查詢中..." : "查詢前十名"}
            </button>
          </div>

          {/* 錯誤訊息 */}
          {error && (
            <div className="mb-6 p-4 bg-red-50 border-l-4 border-red-400 text-red-700">
              {error}
            </div>
          )}

          {/* 資料表格 */}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">排名</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">代號</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">名稱</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">收盤價</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">成交量 (張)</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">漲跌</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {stocks.map((stock, index) => (
                  <tr key={stock.symbol} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-bold text-gray-900">{index + 1}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{stock.symbol}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{stock.name}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-900">{stock.close.toLocaleString()}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-900">
                      {(stock.volume / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                    <td className={`px-6 py-4 whitespace-nowrap text-sm text-right font-medium ${
                      stock.change && stock.change > 0 ? "text-red-600" : stock.change && stock.change < 0 ? "text-green-600" : "text-gray-500"
                    }`}>
                      {stock.change && stock.change > 0 ? `▲ ${stock.change}` : stock.change && stock.change < 0 ? `▼ ${Math.abs(stock.change)}` : "-"}
                    </td>
                  </tr>
                ))}
                {!loading && stocks.length === 0 && !error && (
                  <tr>
                    <td colSpan={6} className="px-6 py-10 text-center text-gray-500 italic">
                      請選擇日期並點擊按鈕查詢
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}