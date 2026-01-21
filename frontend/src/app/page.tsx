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

type Category = "volume" | "ma" | "vma";
type SortOrder = "asc" | "desc";

export default function Home() {
  const [selectedDate, setSelectedDate] = useState("2026-01-19");
  const [category, setCategory] = useState<Category>("volume");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [stocks, setStocks] = useState<StockData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

      console.log(`Fetching: ${apiUrl}${endpoint}`);
      
      // 加入 { cache: 'no-store' } 防止 Next.js 快取舊資料
      const response = await fetch(`${apiUrl}${endpoint}`, { cache: 'no-store' });
      
      if (!response.ok) throw new Error("無法取得資料");
      
      const data = await response.json();
      console.log("API Response Data:", data); 
      setStocks(data);
      if (data.length === 0) setError("該日期無成交資料。");
    } catch (err) {
      console.error(err);
      setError("發生錯誤");
    } finally {
      setLoading(false);
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
        
        <div className="flex flex-wrap gap-4 mb-8 items-end bg-gray-50 p-4 rounded-lg">
          <div>
            <label className="block text-sm mb-1">日期</label>
            <input type="date" value={selectedDate} onChange={(e)=>setSelectedDate(e.target.value)} className="border p-2 rounded"/>
          </div>
          <div>
            <label className="block text-sm mb-1">指標</label>
            <select value={category} onChange={(e)=>setCategory(e.target.value as Category)} className="border p-2 rounded">
              <option value="volume">成交量</option>
              <option value="ma">價格均線 (MA)</option>
              <option value="vma">成交量均線 (VMA)</option>
            </select>
          </div>
          <div>
            <label className="block text-sm mb-1">排序</label>
            <select value={sortOrder} onChange={(e)=>setSortOrder(e.target.value as SortOrder)} className="border p-2 rounded">
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
                {category === "volume" && <th className="p-3 border text-right">成交量(張)</th>}
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
              </tr>
            </thead>
            <tbody>
              {stocks.map((s) => (
                <tr key={s.symbol} className="hover:bg-gray-50">
                  <td className="p-3 border font-mono">{s.symbol}</td>
                  <td className="p-3 border">{s.name}</td>
                  <td className="p-3 border text-right font-bold">{safeFixed(s.close)}</td>
                  
                  {category === "volume" && <td className="p-3 border text-right">{safeVol(s.volume)}</td>}
                  
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
