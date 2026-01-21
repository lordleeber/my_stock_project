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
  ma120?: number;
  ma240?: number;
  vma5?: number;
  vma10?: number;
  vma20?: number;
  vma60?: number;
  vma120?: number;
  vma240?: number;
}

type Category = "volume" | "ma" | "vma";
type SortOrder = "asc" | "desc";

export default function Home() {
  const [selectedDate, setSelectedDate] = useState("");
  const [category, setCategory] = useState<Category>("volume");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  
  const [stocks, setStocks] = useState<StockData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSelectedDate("2026-01-19");
  }, []);

  useEffect(() => {
    // 預設都為遞減 (排行榜)
    setSortOrder("desc");
  }, [category]);

  const fetchData = async () => {
    if (!selectedDate) return;

    setLoading(true);
    setError(null);
    setStocks([]);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      let endpoint = "";
      
      const dateParam = selectedDate.replace(/-/g, "");
      if (category === "volume") {
        endpoint = `/quotes/top-volume?date=${dateParam}&limit=10&sort=${sortOrder}`;
      } else if (category === "ma") {
        endpoint = `/analysis/ma?date=${dateParam}&limit=10&sort=${sortOrder}`;
      } else if (category === "vma") {
        endpoint = `/analysis/vma?date=${dateParam}&limit=10&sort=${sortOrder}`;
      }

      const response = await fetch(`${apiUrl}${endpoint}`);
      if (!response.ok) throw new Error("無法取得資料");
      
      const data = await response.json();
      setStocks(data);
      if (data.length === 0) setError("該日期無成交資料。");
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
          <h1 className="text-3xl font-bold text-gray-900 text-center mb-8">台股市場分析儀表板</h1>

          <div className="bg-gray-100 p-6 rounded-lg mb-8">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">日期</label>
                <input type="date" value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)} className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"/>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">分析指標</label>
                <select value={category} onChange={(e) => setCategory(e.target.value as Category)} className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500">
                  <option value="volume">成交量排行榜</option>
                  <option value="ma">價格均線 (MA)</option>
                  <option value="vma">成交量均線 (VMA)</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">排序方式</label>
                <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value as SortOrder)} className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500">
                  <option value="desc">數值遞減</option>
                  <option value="asc">數值遞增</option>
                </select>
              </div>
              <button onClick={fetchData} disabled={loading} className={`w-full px-4 py-2 rounded-md font-semibold text-white shadow-sm transition-all ${loading ? "bg-gray-400" : "bg-blue-600 hover:bg-blue-700"}`}>
                {loading ? "查詢中..." : "開始分析"}
              </button>
            </div>
          </div>

          {error && <div className="mb-6 p-4 bg-red-50 border-l-4 border-red-400 text-red-700 rounded">{error}</div>}

          <div className="overflow-x-auto border border-gray-200 rounded-lg">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">排名</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">代號</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">名稱</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">收盤價</th>
                  
                  {category === "volume" && <><th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">成交量 (張)</th><th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">漲跌</th></>}
                  {category === "ma" && <><th className="px-4 py-3 text-right text-xs font-medium text-blue-600">MA5</th><th className="px-4 py-3 text-right text-xs font-medium text-orange-600">MA20</th><th className="px-4 py-3 text-right text-xs font-medium text-purple-600">MA60</th></>}
                  {category === "vma" && <><th className="px-4 py-3 text-right text-xs font-medium text-blue-600">VMA5 (張)</th><th className="px-4 py-3 text-right text-xs font-medium text-orange-600">VMA20 (張)</th><th className="px-4 py-3 text-right text-xs font-medium text-purple-600">VMA60 (張)</th></>}
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
                      <><td className="px-4 py-4 whitespace-nowrap text-sm text-right">{(stock.volume / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                        <td className={`px-4 py-4 whitespace-nowrap text-sm text-right font-medium ${stock.change && stock.change > 0 ? "text-red-600" : stock.change && stock.change < 0 ? "text-green-600" : "text-gray-500"}`}>
                          {stock.change && stock.change > 0 ? `▲ ${stock.change}` : stock.change && stock.change < 0 ? `▼ ${Math.abs(stock.change)}` : "-"}
                        </td></>
                    )}
                    {category === "ma" && <><td className="px-4 py-4 text-right text-blue-600">{stock.ma5?.toFixed(2)}</td><td className="px-4 py-4 text-right text-orange-600">{stock.ma20?.toFixed(2)}</td><td className="px-4 py-4 text-right text-purple-600">{stock.ma60?.toFixed(2)}</td></>}
                    {category === "vma" && (
                      <><td className="px-4 py-4 text-right text-blue-600">{((stock.vma5 || 0) / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                        <td className="px-4 py-4 text-right text-orange-600">{((stock.vma20 || 0) / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                        <td className="px-4 py-4 text-right text-purple-600">{((stock.vma60 || 0) / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td></>
                    )}
                  </tr>
                ))}
                {!loading && stocks.length === 0 && !error && (
                  <tr>
                    <td colSpan={8} className="px-6 py-12 text-center text-gray-400 italic">
                      請設定上方條件並點擊「開始分析」
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