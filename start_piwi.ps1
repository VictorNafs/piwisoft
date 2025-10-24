# start_piwi.ps1 — lance l'UI principale ; l'UI décidera d'ouvrir l'installeur si nécessaire.
# Compatible PowerShell 5+ ; pas besoin d'élévation. Idempotent et silencieux.

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms | Out-Null

function Get-AppDir {
  if ($PSScriptRoot) { return $PSScriptRoot }
  return Split-Path -Parent $MyInvocation.MyCommand.Path
}

try {
  $base = Get-AppDir

  $exe = Join-Path $base "piwi_gui_win.exe"
  $py  = Join-Path $base "piwi_gui_win.py"

  if (Test-Path -LiteralPath $exe) {
    Start-Process -FilePath $exe -WorkingDirectory $base
    exit 0
  }

  if (Test-Path -LiteralPath $py) {
    $pyw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue)?.Source
    if ($pyw) {
      Start-Process -FilePath $pyw -ArgumentList @("$py") -WorkingDirectory $base
    } else {
      Start-Process -FilePath "python.exe" -ArgumentList @("$py") -WorkingDirectory $base
    }
    exit 0
  }

  [System.Windows.Forms.MessageBox]::Show(
    "Piwi introuvable dans $base.`nRéinstallez Piwi.",
    "Piwi",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Error
  ) | Out-Null
  exit 1

} catch {
  try {
    [System.Windows.Forms.MessageBox]::Show(
      "Erreur au lancement: $($_.Exception.Message)",
      "Piwi",
      [System.Windows.Forms.MessageBoxButtons]::OK,
      [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
  } catch {}
  exit 2
}
