# download_latest_rootfs.ps1
# Downloads RootFS & checksum from GitHub Releases, verifies SHA256, and places them under .\wsl\
param(
  [string]$RepoBaseUrl = "https://github.com/VictorNafs/rootfs-helper/releases/download/rootfs-stable",
  [string]$OutDir = ".\wsl",
  [string]$RootfsName = "ubuntu-jammy-wsl-amd64-ubuntu22.04lts.rootfs.tar.gz",
  [string]$ShaName = "piwi-rootfs.sha256"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if (-not (Test-Path -LiteralPath $OutDir)) {
  New-Item -ItemType Directory -Path $OutDir | Out-Null
}

$rootfsUrl = "$RepoBaseUrl/$RootfsName"
$shaUrl    = "$RepoBaseUrl/$ShaName"
$rootfsOut = Join-Path $OutDir $RootfsName
$shaOut    = Join-Path $OutDir $ShaName

Write-Host "[DL] RootFS: $rootfsUrl"
Invoke-WebRequest -Uri $rootfsUrl -OutFile $rootfsOut

Write-Host "[DL] SHA256: $shaUrl"
Invoke-WebRequest -Uri $shaUrl -OutFile $shaOut

# Read expected sha256 (supports either 'hex  filename' or just hex on first line)
$shaText = Get-Content -LiteralPath $shaOut -Raw
$expected = ($shaText -split '\s+')[0].ToUpperInvariant()

Write-Host "[CHK] Verifying SHA256..."
$actual = (Get-FileHash -LiteralPath $rootfsOut -Algorithm SHA256).Hash.ToUpperInvariant()

if ($expected -ne $actual) {
  Write-Host "[ERR] SHA256 mismatch!"
  Write-Host "      expected: $expected"
  Write-Host "      actual  : $actual"
  Remove-Item -LiteralPath $rootfsOut -Force -ErrorAction SilentlyContinue
  exit 1
}

Write-Host "[OK] RootFS verified."
exit 0
