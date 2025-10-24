param (
  [string]$Codename = "jammy",
  [string]$OutputFolder = ".\wsl"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Filename = "ubuntu-$Codename-wsl-amd64-wsl.rootfs.tar.gz"
$BaseUrl  = "https://cloud-images.ubuntu.com/wsl/releases/$Codename/current"
$OutPath  = Join-Path $OutputFolder $Filename
$Url      = "$BaseUrl/$Filename"

if (-not (Test-Path -LiteralPath $OutputFolder)) {
  New-Item -ItemType Directory -Path $OutputFolder | Out-Null
}

if ($PSVersionTable.PSVersion.Major -lt 6) {
  try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
}

Invoke-WebRequest -Uri $Url -OutFile $OutPath

if (-not (Test-Path -LiteralPath $OutPath)) {
  throw "Download failed: $OutPath"
}

# IMPORTANT: print ONLY the filename for the .bat FOR /F capture
[Console]::Out.Write($Filename)
