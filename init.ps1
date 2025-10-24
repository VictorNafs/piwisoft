# PowerShell -NoProfile -ExecutionPolicy Bypass -File .\init.ps1


param(
  [string]$DistroName = "PiwiUbuntu",
  [string]$BaseDir    = "$env:USERPROFILE\Piwi\wsl\PiwiUbuntu"  # dossier où ext4.vhdx est importé
)

Write-Host "=== Reset WSL distro: $DistroName ==="

# 1) Arrêter WSL
wsl --shutdown | Out-Null

# 2) Tentative d’unregister propre
$null = wsl --unregister $DistroName 2>&1
if ($LASTEXITCODE -eq 0) {
  Write-Host "Unregister OK via WSL."
} else {
  Write-Warning "wsl --unregister a échoué ($LASTEXITCODE). On nettoie le registre."

  $lxss = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
  $found = $false
  Get-ChildItem $lxss -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
    if ($p.DistributionName -eq $DistroName) {
      Remove-Item $_.PSPath -Recurse -Force
      Write-Host "Removed registry key:" $_.PSChildName
      $found = $true
    }
  }
  if (-not $found) {
    Write-Host "Aucune clé registre trouvée pour $DistroName (déjà nettoyée ?)."
  }
}

# 3) Supprimer le dossier d’import si présent
if (Test-Path -LiteralPath $BaseDir) {
  try {
    Remove-Item -LiteralPath $BaseDir -Recurse -Force
    Write-Host "Removed folder: $BaseDir"
  } catch {
    Write-Warning "Impossible de supprimer $BaseDir : $($_.Exception.Message)"
  }
} else {
  Write-Host "Dossier absent (OK) : $BaseDir"
}

# 4) (Optionnel) Redémarrer le service WSL
try {
  Restart-Service -Name LxssManager -ErrorAction Stop
  Write-Host "LxssManager redémarré."
} catch {
  Write-Host "Pas d'admin ? LxssManager non redémarré. Ce n'est pas bloquant."
}

# 5) Vérification
$names = wsl -l -q 2>$null
if ($names -match [regex]::Escape($DistroName)) {
  Write-Warning "$DistroName est encore listée. Déconnecte ta session Windows ou reboot si besoin."
} else {
  Write-Host "OK : $DistroName n'est plus listée."
}
