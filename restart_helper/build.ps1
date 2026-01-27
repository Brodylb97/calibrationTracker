# Build RestartHelper.exe with MinGW gcc or LLVM-MinGW clang.
# Run from repo root or from restart_helper\.
Set-Location $PSScriptRoot

$compiler = $null
if (Get-Command gcc -ErrorAction SilentlyContinue) { $compiler = "gcc" }
elseif (Get-Command clang -ErrorAction SilentlyContinue) { $compiler = "clang" }

if (-not $compiler) {
    Write-Host "gcc and clang not found on PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "Install a compiler, then open a new terminal and run this again:"
    Write-Host ""
    Write-Host "  Option A (PowerShell / winget):"
    Write-Host "    winget install -e --id MartinStorsjo.LLVM-MinGW.UCRT"
    Write-Host "    (add its bin to PATH if needed; often under Program Files)"
    Write-Host ""
    Write-Host "  Option B (MSYS2):"
    Write-Host "    Open 'MSYS2 MinGW 64-bit', run: pacman -S mingw-w64-x86_64-gcc"
    Write-Host "    Then in that shell: cd restart_helper && gcc -O2 -o RestartHelper.exe restart_helper.c -mwindows"
    Write-Host ""
    exit 1
}

& $compiler -O2 -o RestartHelper.exe restart_helper.c -mwindows
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Built RestartHelper.exe"
Write-Host "Copy to dist\RestartHelper.exe before building the installer."
