$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$AppDir = Resolve-Path $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "Python virtual environment not found: $Python"
}

& $Python -m pip install -r (Join-Path $AppDir "requirements.txt")

& $Python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name EdgeTTSConverter `
  --distpath (Join-Path $AppDir "dist") `
  --workpath (Join-Path $AppDir "build") `
  --specpath $AppDir `
  (Join-Path $AppDir "edge_tts_converter.py")

$PackageDir = Join-Path $AppDir "dist\EdgeTTSConverter"
Copy-Item -LiteralPath (Join-Path $AppDir "README.md") -Destination $PackageDir -Force

Write-Host ""
Write-Host "Built portable package:"
Write-Host $PackageDir
