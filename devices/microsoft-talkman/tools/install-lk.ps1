# Puts BootShim and LK on a Lumia 950's EFIESP, in USB mass storage mode. Touches
# no partition table and nothing but EFIESP. Takes the files from
# Android4Lumia950/installer (commit be3ed23, DATA/ and ui/), each checked here
# against its SHA-256, and its BCD with one change: the FFU loader's key combination
# put back, so that flash mode stays reachable from the buttons.
#
#   powershell -ExecutionPolicy Bypass -File install-lk.ps1 -Data <DATA folder> -Ui <ui folder> -Backup <folder holding a copy of EFIESP>
#
# Needs an administrator's PowerShell.
param(
	[Parameter(Mandatory = $true)][string]$Data,
	[Parameter(Mandatory = $true)][string]$Ui,
	[Parameter(Mandatory = $true)][string]$Backup
)
$ErrorActionPreference = "Stop"

$hashes = @{
	"BCD" = "ed0e23ce0aa7a36cd9260b478deb6e767261b0a1755ec1b518047bf0028903db"
	"Stage2.efi" = "80dc6e29e7448f095b050a2234a29afe6daf68c4605354114a8a49db696ff5db"
	"bootshim.efi" = "108b070195f59aac27ddd0ee1d2a806ec1e267d22c2a763d95dcac9c72912a18"
	"developermenu.efi" = "107b5c160343fe008244b1c20a0723807cbcca8bcc765c14ee8c645b9953c892"
	"emmc_appsboot.mbn" = "62fb8b73e14c5045300f3c2158d146f8a5345045152c17f61bca8d07af7cf5a2"
}
function Sha($path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLower() }

foreach ($name in $hashes.Keys) {
	if ((Sha (Join-Path $Data $name)) -ne $hashes[$name]) { throw "$name is not the file this script expects" }
}

$disk = @(Get-Disk | Where-Object { $_.BusType -eq "USB" -and $_.FriendlyName -like "MSFT Phone*" -and $_.Size -gt 20GB -and $_.Size -lt 40GB })
if ($disk.Count -ne 1) { throw "need exactly one phone disk in mass storage mode, found $($disk.Count)" }
$part = $null
foreach ($p in Get-Partition -DiskNumber $disk[0].Number) {
	$v = $p | Get-Volume -ErrorAction SilentlyContinue
	if ($v -and $v.FileSystemLabel -eq "EFIESP") { $part = $p }
}
if (-not $part) { throw "no EFIESP on the phone" }
if (-not $part.DriveLetter -or $part.DriveLetter -eq [char]0) {
	$part | Add-PartitionAccessPath -AssignDriveLetter
	$part = Get-Partition -DiskNumber $disk[0].Number -PartitionNumber $part.PartitionNumber
}
$esp = "$($part.DriveLetter):"
$bcdOnPhone = Join-Path $esp "EFI\Microsoft\Boot\BCD"
$bootDir = Join-Path $esp "Windows\System32\BOOT"
if (-not (Test-Path $bcdOnPhone) -or -not (Test-Path $bootDir)) { throw "$esp does not look like a Lumia's EFIESP" }

# Never overwrite what no copy exists of
$saved = Join-Path $Backup "EFI\Microsoft\Boot\BCD"
if ((Sha $saved) -ne (Sha $bcdOnPhone)) { throw "the BCD in $Backup is not the phone's: back EFIESP up first" }

# The BCD, with the FFU loader back on its key
$FFU = "{0ff5f24a-3785-4aeb-b8fe-4226215b88c4}"
$BOOTMGR = "{9dea862c-5cdd-4e70-acc1-f32b344d4795}"
$work = Join-Path $env:TEMP "ztos-talkman-bcd"
New-Item -ItemType Directory -Force -Path $work | Out-Null
$bcd = Join-Path $work "BCD"
Copy-Item -LiteralPath (Join-Path $Data "BCD") -Destination $bcd -Force
& bcdedit /store $bcd /set $BOOTMGR "custom:54000001" $FFU | Out-Null
if ($LASTEXITCODE -ne 0) { throw "bcdedit could not change the BCD copy" }
$check = (& bcdedit /store $bcd /enum $BOOTMGR /v) -join "`n"
if ($check -notmatch "custom:54000001\s+\{0ff5f24a") { throw "the BCD copy lost the FFU loader's key" }

$files = @(
	@{ From = $bcd; To = $bcdOnPhone }
	@{ From = (Join-Path $Data "bootshim.efi"); To = (Join-Path $bootDir "bootshim.efi") }
	@{ From = (Join-Path $Data "developermenu.efi"); To = (Join-Path $bootDir "developermenu.efi") }
	@{ From = (Join-Path $Data "Stage2.efi"); To = (Join-Path $esp "Stage2.efi") }
	@{ From = (Join-Path $Data "emmc_appsboot.mbn"); To = (Join-Path $esp "emmc_appsboot.mbn") }
)
# (their ui/ also carries a partition.sh, which is no part of the menu)
foreach ($f in Get-ChildItem -LiteralPath $Ui -Filter "*.bmpx") {
	$files += @{ From = $f.FullName; To = (Join-Path $bootDir "ui\$($f.Name)") }
}
foreach ($f in $files) {
	Copy-Item -LiteralPath $f.From -Destination $f.To -Force
	Write-Output "wrote $($f.To)"
}
Write-VolumeCache -DriveLetter $part.DriveLetter

foreach ($f in $files) {
	if ((Sha $f.From) -ne (Sha $f.To)) { throw "read back differs: $($f.To)" }
}
Write-Output "DONE: $($files.Count) files on $esp, each read back and compared"
