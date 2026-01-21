"use client";

import { useState, useEffect } from "react";

interface StockData {
  date: string;
  symbol: string;
  name: string;
  close: number;
  volume: number;
  change?: number | null;
  k?: number;
  d?: number;
  rsi?: number;
  ma5?: number;
  ma10?: number;
  ma20?: number;
  ma60?: number;
  ma120?: number;
  ma240?: number;
}

type Category = "volume" | "kd" | "rsi" | "ma";
type SortOrder = "asc" | "desc";

export default function Home() {
  const [selectedDate, setSelectedDate] = useState("");
  const [category, setCategory] = useState<Category>("volume");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  
  const [stocks, setStocks] = useState<StockData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 初始化日期
  useEffect(() => {
    // 若有資料，預設一個已知的交易日
    setSelectedDate("2026-01-19");
  }, []);

  // 當類別改變時調整預設排序
  useEffect(() => {
    if (category === "volume") setSortOrder("desc");
    else if (category === "kd" || category === "rsi") setSortOrder("asc");
    else if (category === "ma") setSortOrder("desc"); // MA 預設以成交量由大到小排
  }, [category]);

  const fetchData = async () => {
    if (!selectedDate) return;

    setLoading(true);
    setError(null);
    setStocks([]);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      let endpoint = "";
      
      if (category === "volume") {
        endpoint = `/quotes/top-volume?date=${selectedDate.replace(/-/g, "")}&limit=10&sort=${sortOrder}`;
      } else if (category === "kd") {
        endpoint = `/analysis/kd-rank?date=${selectedDate.replace(/-/g, "")}&limit=10&sort=${sortOrder}`;
      } else if (category === "rsi") {
        endpoint = `/analysis/rsi-rank?date=${selectedDate.replace(/-/g, "")}&limit=10&sort=${sortOrder}`;
      } else if (category === "ma") {
        endpoint = `/analysis/ma?date=${selectedDate.replace(/-/g, "")}&limit=10&sort=${sortOrder}`;
      }

      const response = await fetch(`${apiUrl}${endpoint}`);
      
      if (!response.ok) {
        throw new Error("無法取得資料，請確認後端是否啟動或該日期是否有資料。");
      }
      
      const data = await response.json();
      setStocks(data);
      if (data.length === 0) {
        setError("該日期無符合條件的資料。");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "發生未知錯誤");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-6xl mx-auto">
        <div className="bg-white shadow-xl rounded-2xl p-8">
          <h1 className="text-3xl font-bold text-gray-900 text-center mb-8">
            台股市場分析儀表板
          </h1>

          <div className="bg-gray-100 p-6 rounded-lg mb-8">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div>
                <label htmlFor="date" className="block text-sm font-medium text-gray-700 mb-1">日期</label>
                <input
                  type="date"
                  id="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              <div>
                <label htmlFor="category" className="block text-sm font-medium text-gray-700 mb-1">分析指標</label>
                <select
                  id="category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value as Category)}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="volume">成交量 (Volume)</option>
                  <option value="kd">KD 指標 (Stochastic)</option>
                  <option value="rsi">RSI 指標 (Strength)</option>
                  <option value="ma">移動平均線 (MA)</option>
                </select>
              </div>

              <div>
                <label htmlFor="sort" className="block text-sm font-medium text-gray-700 mb-1">排序方式</label>
                <select
                  id="sort"
                  value={sortOrder}
                  onChange={(e) => setSortOrder(e.target.value as SortOrder)}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="desc">數值由大到小 (遞減)</option>
                  <option value="asc">數值由小到大 (遞增)</option>
                </select>
              </div>

              <button
                onClick={fetchData}
                disabled={loading}
                className={`w-full px-4 py-2 rounded-md font-semibold text-white shadow-sm transition-all ${
                  loading ? "bg-gray-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700 active:scale-95"
                }`}
              >
                {loading ? "查詢中..." : "開始分析"}
              </button>
            </div>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-50 border-l-4 border-red-400 text-red-700 rounded">
              {error}
            </div>
          )}

          <div className="overflow-x-auto border border-gray-200 rounded-lg">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">排名</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">代號</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">名稱</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">收盤價</th>
                  
                  {category === "volume" && (
                    <>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">成交量 (張)</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">漲跌</th>
                    </>
                  )}
                  {category === "kd" && (
                    <>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">K 值</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">D 值</th>
                    </>
                  )}
                  {category === "rsi" && (
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">RSI(14)</th>
                  )}
                  {category === "ma" && (
                    <>
                      <th className="px-4 py-3 text-right text-xs font-medium text-blue-600 uppercase tracking-wider">MA5</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-orange-600 uppercase tracking-wider">MA20</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-purple-600 uppercase tracking-wider">MA60</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {stocks.map((stock, index) => (
                  <tr key={stock.symbol} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-4 whitespace-nowrap text-sm font-bold text-gray-500">{index + 1}</td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm font-mono text-blue-600">{stock.symbol}</td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{stock.name}</td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm text-right font-bold">{stock.close.toLocaleString()}</td>

                    {category === "volume" && (
                      <>
                        <td className="px-4 py-4 whitespace-nowrap text-sm text-right">{(stock.volume / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                        <td className={`px-4 py-4 whitespace-nowrap text-sm text-right font-medium ${stock.change && stock.change > 0 ? "text-red-600" : stock.change && stock.change < 0 ? "text-green-600" : "text-gray-500"}`}>
                          {stock.change && stock.change > 0 ? `▲ ${stock.change}` : stock.change && stock.change < 0 ? `▼ ${Math.abs(stock.change)}` : "-"}
                        </td>
                      </>
                    )}
                    
                    {category === "kd" && (
                      <>
                        <td className="px-4 py-4 whitespace-nowrap text-sm text-right font-bold text-blue-700">{stock.k?.toFixed(2)}</td>
                        <td className="px-4 py-4 whitespace-nowrap text-sm text-right text-orange-600">{stock.d?.toFixed(2)}</td>
                      </>
                    )}

                    {category === "rsi" && (
                      <td className="px-4 py-4 whitespace-nowrap text-sm text-right font-bold text-purple-700">{stock.rsi?.toFixed(2)}</td>
                    )}

                    {category === "ma" && (
                      <>
                        <td className="px-4 py-4 whitespace-nowrap text-sm text-right text-blue-600 font-medium">{stock.ma5?.toFixed(2)}</td>
                        <td className="px-4 py-4 whitespace-nowrap text-sm text-right text-orange-600 font-medium">{stock.ma20?.toFixed(2)}</td>
                        <td className="px-4 py-4 whitespace-nowrap text-sm text-right text-purple-600 font-medium">{stock.ma60?.toFixed(2)}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}