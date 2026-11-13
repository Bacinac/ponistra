"""What Excel saves for the tests, in one folder: `python -m apps.engine.tests.excel <folder>
[part ...]` writes, for each language, the workbooks of cases, matching and the sweep without
values, the entries of implied, the grammar's workbooks and the workbook of codes of each closed
table in its languages, or only the PARTS it is given, with the function Excel types the entries
with (implied.MACRO), etalons.ps1, which has Excel save them on Windows under the regional format
of their language, and watch.ps1, which runs it whenever the folder changes:

    powershell -NoProfile -ExecutionPolicy Bypass -File <folder>\\etalons.ps1 `
        [-Languages en-GB,de] [-Names cases]

A workbook <name>-<language>-codes.xlsx or entries <name>-<language>.tsv newer than
<name>-<language>.xlsx are waiting, as is each one named. For each language with something waiting
it sets the regional format (Set-Culture), starts Excel, writes the settings
Application.International tells as international-<language>.tsv, has it compute and save each
workbook as <name>-<language>.xlsx, with a CSV of what each cell shows where the name holds
"opened", and type each entries file into a workbook of its name with a CSV of what each cell shows
and a TSV of how it writes each format in the language beside it, and quits it. One waiting that
Excel fails is renamed .failed, one named stops the run. The regional format the user had, with
anything changed in it by hand, comes back from a copy of the registry taken first, as does
Excel's trust of access to VBA projects, which adding the function needs. A run stopped before it
restored the copy leaves it for the next one, which restores it rather than taking the language it
was stopped in as the user's. Excel must be closed: one already open would see the regional format
change under it."""

import sys
from pathlib import Path

from apps.engine.formats import CULTURES
from apps.engine.tests import cases, closed, grammar, implied, matching, sweep

# Excel's country of each culture (Application.International(xlCountrySetting)).
COUNTRIES = {"hr": 385, "en": 1, "en-GB": 44, "de": 49, "fr": 33, "it": 39, "es": 34}
# The settings Application.International tells, from xlCountryCode to xlTimeLeadingZero.
INTERNATIONAL = 45
BOOKS = {"cases": cases, "matching": matching, "sweep": sweep}
PARTS = (*BOOKS, "implied", "grammar", *closed.PARTS)
TYPED = ("implied",)
SCRIPT = r"""param([string[]]$Languages = @({languages}), [string[]]$Names = @())
$ErrorActionPreference = 'Stop'
$Languages = $Languages -split ','
$Names = @($Names -split ',' | Where-Object {{ $_ }})
$cultures = @{{ {cultures} }}
$countries = @{{ {countries} }}
$typed = @({typed})
$unknown = $Languages | Where-Object {{ -not $cultures.ContainsKey($_) }}
if ($unknown) {{ throw "PONISTRA: no such language: $unknown" }}
$here = $PSScriptRoot
function Waiting($source, $result) {{
    if (-not (Test-Path $result)) {{ return $true }}
    (Get-Item $result).LastWriteTime -lt (Get-Item $source).LastWriteTime
}}
$opened = [ordered]@{{}}
$entered = @{{}}
foreach ($code in $Languages) {{
    $escaped = [regex]::Escape($code)
    $codes = Get-ChildItem $here -Filter "*-$code-codes.xlsx" | Sort-Object Name
    $books = @(foreach ($each in $codes) {{
        if ($each.Name -notmatch "^(.+)-$escaped-codes\.xlsx$") {{ continue }}
        $name = $Matches[1]
        $result = Join-Path $here "$name-$code.xlsx"
        if ($name -in $Names -or (Waiting $each.FullName $result)) {{ $name }}
    }})
    $entries = @(foreach ($name in $typed) {{
        $path = Join-Path $here "$name-$code.tsv"
        if (-not (Test-Path $path)) {{ continue }}
        if ($name -in $Names -or (Waiting $path (Join-Path $here "$name-$code.xlsx"))) {{ $name }}
    }})
    if ($books -or $entries) {{
        $opened[$code] = $books
        $entered[$code] = $entries
    }}
}}
$found = @($opened.Values | ForEach-Object {{ $_ }}) + @($entered.Values | ForEach-Object {{ $_ }})
$missing = $Names | Where-Object {{ $_ -notin $found }}
if ($missing) {{ throw "PONISTRA: nothing to save for $missing" }}
if (-not $opened.Count) {{ exit }}
if (Get-Process EXCEL -ErrorAction SilentlyContinue) {{
    Write-Host 'PONISTRA: close Excel first, it would see the regional format change under it'
    exit 2
}}
Add-Type -Namespace Ponistra -Name Native -MemberDefinition @'
[DllImport("user32.dll", CharSet = CharSet.Unicode)]
public static extern IntPtr SendMessageTimeout(IntPtr window, uint message, UIntPtr w, string l,
    uint flags, uint timeout, out UIntPtr result);
[DllImport("user32.dll")]
public static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);
'@
Get-ChildItem $here | Unblock-File
$saved = Join-Path $env:LOCALAPPDATA 'Ponistra'
New-Item $saved -ItemType Directory -Force | Out-Null
$named = Join-Path $saved 'International.txt'
$copy = Join-Path $saved 'International.reg'
if (-not (Test-Path $copy)) {{
    Set-Content $named (Get-Culture).Name
    cmd /c "reg export ""HKCU\Control Panel\International"" ""$copy"" /y >nul 2>&1"
    if ($LASTEXITCODE -ne 0) {{ throw 'PONISTRA: the regional format could not be copied' }}
}}
$own = Get-Content $named
# Excel saves into a folder of its own and the workbook is moved after: saved straight onto a
# shared folder, about half of them stall for 35 s.
$local = Join-Path $saved 'books'
New-Item $local -ItemType Directory -Force | Out-Null
$security = 'HKCU:\Software\Microsoft\Office\16.0\Excel\Security'
if (-not (Test-Path $security)) {{ New-Item $security | Out-Null }}
$trusted = (Get-ItemProperty $security).AccessVBOM
Set-ItemProperty $security -Name AccessVBOM -Value 1 -Type DWord
$macro = Get-Content (Join-Path $here 'Implied.bas') -Raw -Encoding UTF8
function Seconds($since) {{ [int]((Get-Date) - $since).TotalSeconds }}
function Failed($code, $name, $path, $reason) {{
    if ($name -in $Names) {{ throw "PONISTRA: $code ${{name}}: $reason" }}
    Write-Host ('{{0}} {{1}}: FAILED {{2}}' -f $code, $name, $reason)
    Rename-Item $path ((Split-Path $path -Leaf) + '.failed') -Force
}}
$began = Get-Date
try {{
    foreach ($code in $opened.Keys) {{
        Set-Culture $cultures[$code]
        Write-Host "${{code}}: starting Excel"
        $excel = New-Object -ComObject Excel.Application
        [uint32]$process = 0
        [void][Ponistra.Native]::GetWindowThreadProcessId([IntPtr]$excel.Hwnd, [ref]$process)
        try {{
            $excel.Visible = $true
            $excel.DisplayAlerts = $false
            $excel.ScreenUpdating = $false
            $excel.EnableEvents = $false
            $told = foreach ($index in 1..{international}) {{
                try {{ "$index`t$($excel.International($index))" }} catch {{ "$index`t#N/A" }}
            }}
            Set-Content (Join-Path $here "international-$code.tsv") $told -Encoding UTF8
            foreach ($name in $opened[$code]) {{
                $at = Get-Date
                $path = Join-Path $here "$name-$code-codes.xlsx"
                $book = $null
                try {{
                    $book = $excel.Workbooks.Open($path)
                    $excel.CalculateFull()
                    $book.SaveAs((Join-Path $local "$name-$code.xlsx"), 51)
                    if ($name -like '*opened*') {{
                        $m = [Type]::Missing
                        $book.Worksheets.Item(1).UsedRange.Columns.AutoFit() | Out-Null
                        $book.SaveAs((Join-Path $local "$name-$code-shown.csv"), 62,
                            $m, $m, $m, $m, $m, $m, $m, $m, $m, $true)
                    }}
                    $book.Close($false)
                    Get-ChildItem $local -Filter "$name-$code*" |
                        Where-Object {{ $_.Name -in "$name-$code.xlsx", "$name-$code-shown.csv" }} |
                        Move-Item -Destination $here -Force
                }} catch {{
                    if ($book) {{ $book.Close($false) }}
                    Failed $code $name $path $_.Exception.Message
                    continue
                }}
                Write-Host ('{{0}} {{1}}: {{2}} s' -f $code, $name, (Seconds $at))
            }}
            if ($entered[$code]) {{
                $holder = $excel.Workbooks.Add()
                $holder.VBProject.VBComponents.Add(1).CodeModule.AddFromString($macro)
                foreach ($name in $entered[$code]) {{
                    $at = Get-Date
                    $path = Join-Path $here "$name-$code.tsv"
                    $result = $excel.Run("'$($holder.Name)'!Implied", $path, $countries[$code])
                    if ($result -like 'NOT SAVED*') {{
                        Failed $code $name $path $result
                        continue
                    }}
                    $took = Seconds $at
                    Write-Host ('{{0}} {{1}}: {{2}}, {{3}} s' -f $code, $name, $result, $took)
                }}
                $holder.Close($false)
            }}
        }} finally {{
            $book = $null
            $holder = $null
            $excel.Quit()
            [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
            $excel = $null
            [GC]::Collect()
            [GC]::WaitForPendingFinalizers()
            Wait-Process -Id $process -Timeout 20 -ErrorAction SilentlyContinue
            Stop-Process -Id $process -Force -ErrorAction SilentlyContinue
        }}
    }}
}} finally {{
    Set-Culture $own
    cmd /c "reg import ""$copy"" >nul 2>&1"
    $restored = $LASTEXITCODE -eq 0
    if ($null -eq $trusted) {{
        Remove-ItemProperty $security -Name AccessVBOM
    }} else {{
        Set-ItemProperty $security -Name AccessVBOM -Value $trusted -Type DWord
    }}
    $out = [UIntPtr]::Zero
    [void][Ponistra.Native]::SendMessageTimeout(
        [IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, 'intl', 2, 5000, [ref]$out)
    if ($restored) {{
        Remove-Item $copy, $named
    }} else {{
        Write-Host "PONISTRA: restore the regional format from $copy" -ForegroundColor Red
    }}
    Write-Host ('PONISTRA: {{0}} s, regional format {{1}} again' -f (Seconds $began), $own)
}}
"""
# Started at logon by a scheduled task in the user's session, as Excel needs a desktop. A failed run
# is not repeated until etalons.ps1 changes; one that found Excel open is, once it closes.
WATCH = r"""$ErrorActionPreference = 'Continue'
$alone = New-Object System.Threading.Mutex($false, 'Local\PonistraEtalons')
if (-not $alone.WaitOne(0)) { exit }
$here = $PSScriptRoot
$script = Join-Path $here 'etalons.ps1'
$log = Join-Path $here 'watch.log'
function Say($line) { Add-Content $log ('{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $line) }
Say ('watching on ' + $env:COMPUTERNAME)
$last = [datetime]::MinValue
$broken = $null
$waiting = $false
while ($true) {
    Start-Sleep -Seconds 10
    if (-not (Test-Path $script)) { continue }
    if ($broken -and (Get-Item $script).LastWriteTime -eq $broken) { continue }
    if (-not (Get-ChildItem $here -File | Where-Object { $_.LastWriteTime -gt $last })) { continue }
    if (Get-Process EXCEL -ErrorAction SilentlyContinue) {
        if (-not $waiting) { Say 'waiting for Excel to close' }
        $waiting = $true
        continue
    }
    $waiting = $false
    $last = Get-Date
    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $script 2>&1 | Out-String
    $output = $output.Trim()
    if ($LASTEXITCODE -eq 2) {
        $last = [datetime]::MinValue
    } elseif ($LASTEXITCODE -ne 0) {
        $broken = (Get-Item $script).LastWriteTime
        Say "FAILED`n$output"
    } else {
        $broken = $null
        if ($output) { Say $output }
    }
}
"""


def _listed(values) -> str:
    return "; ".join(f"'{key}' = {value}" for key, value in values)


def _quoted(names) -> str:
    return ", ".join(f"'{name}'" for name in names)


def script(parts=PARTS) -> str:
    return SCRIPT.format(
        languages=_quoted(CULTURES),
        cultures=_listed((code, f"'{name}'") for code, name in CULTURES.items()),
        countries=_listed(COUNTRIES.items()),
        typed=_quoted(name for name in TYPED if name in parts),
        international=INTERNATIONAL,
    )


def write(folder: Path, parts=PARTS) -> None:
    if unknown := set(parts) - set(PARTS):
        raise SystemExit(f"no such part: {', '.join(sorted(unknown))}")
    folder.mkdir(parents=True, exist_ok=True)
    for name, module in BOOKS.items():
        if name in parts:
            book = module.workbook()
            for code in CULTURES:
                book.save(folder / f"{name}-{code}-codes.xlsx")
    if "implied" in parts:
        for code in CULTURES:
            implied.write(code, folder / f"implied-{code}.tsv")
    if "grammar" in parts:
        grammar.write(folder)
    for table, part in zip(closed.TABLES + closed.CHECKS, closed.PARTS, strict=True):
        if part in parts:
            closed.write(folder, table)
    (folder / "Implied.bas").write_text(implied.MACRO.replace("\n", "\r\n"), encoding="utf-8")
    for name, text in (("etalons.ps1", script(parts)), ("watch.ps1", WATCH)):
        (folder / name).write_text("\ufeff" + text.replace("\n", "\r\n"), encoding="utf-8")


if __name__ == "__main__":
    write(Path(sys.argv[1]), sys.argv[2:] or PARTS)
