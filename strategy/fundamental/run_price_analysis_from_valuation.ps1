param(
    [string[]]$Markets = @("sii", "otc"),
    [string[]]$Quarters = @(
        "2021Q1","2021Q2","2021Q3","2021Q4",
        "2022Q1","2022Q2","2022Q3","2022Q4",
        "2023Q1","2023Q2","2023Q3","2023Q4",
        "2024Q1","2024Q2","2024Q3","2024Q4",
        "2025Q1","2025Q2","2025Q3"
    ),
    [string]$PythonExe = ".\.venv\Scripts\python.exe"
)

function Get-NextQuarter([string]$q) {
    $y = [int]$q.Substring(0,4)
    $n = [int]$q.Substring(5,1)
    if ($n -eq 4) {
        return ("{0}Q1" -f ($y + 1))
    }
    return ("{0}Q{1}" -f $y, ($n + 1))
}

$ok = 0
$fail = 0
$miss = 0

foreach ($m in $Markets) {
    foreach ($q in $Quarters) {
        $nq = Get-NextQuarter $q
        $reportPath = "strategy/fundamental/valuation_report_{0}_{1}.csv" -f $q, $m

        if (-not (Test-Path $reportPath)) {
            Write-Host ("MISS {0}" -f $reportPath)
            $miss++
            continue
        }

        Write-Host ("RUN {0} -> {1} {2}" -f $q, $nq, $m)
        & $PythonExe strategy/fundamental/price_range_analyzer.py `
            --start-quarter $q `
            --end-quarter $nq `
            --report-path $reportPath `
            --market $m

        if ($LASTEXITCODE -eq 0) {
            $ok++
        } else {
            $fail++
        }
    }
}

Write-Host ("DONE ok={0} fail={1} miss={2}" -f $ok, $fail, $miss)
if ($fail -gt 0) {
    exit 1
}
