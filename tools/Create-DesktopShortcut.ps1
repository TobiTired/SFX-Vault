param([string]$Destination)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$shortcutPath = if ($Destination) { [IO.Path]::GetFullPath($Destination) } else { Join-Path ([Environment]::GetFolderPath('Desktop')) 'SFX Vault V0.6.lnk' }
if (Test-Path -LiteralPath $shortcutPath) { throw "Shortcut already exists: $shortcutPath" }
$packagedExe = Join-Path $projectRoot 'dist\SFX Vault\SFX Vault.exe'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
if (Test-Path -LiteralPath $packagedExe) {
    $shortcut.TargetPath = $packagedExe
} else {
    $shortcut.TargetPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
    $shortcut.Arguments = '-m sfx_vault'
}
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = (Join-Path $projectRoot 'sfx_vault\assets\sfx-vault.ico') + ',0'
$shortcut.Description = 'SFX Vault — local sound library'
$shortcut.Save()
Write-Output "Created $shortcutPath"
