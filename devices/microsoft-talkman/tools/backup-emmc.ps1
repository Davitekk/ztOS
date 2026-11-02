# A full, read-only copy of a Lumia 950's eMMC, taken in USB mass storage mode.
#
#   powershell -ExecutionPolicy Bypass -File backup-emmc.ps1 -Out H:\ztos-talkman-backup
#   ... -Check    only says which disk it would read
#
# The copy holds the phone's identity (IMEI, modem calibration, Wi-Fi and
# Bluetooth addresses): keep it private, never commit it. It needs an
# administrator's PowerShell, and it opens the disk for reading only.
param(
	[string]$Out = "",
	[switch]$Check
)
$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class ZtosRawDisk {
	[DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
	public static extern SafeFileHandle CreateFileW(string name, uint access, uint share,
		IntPtr security, uint disposition, uint flags, IntPtr template);
}
"@

# Only a USB disk of an eMMC's size that carries the Windows Phone volumes. An
# SD card in the phone, a USB stick or a computer's own disk never passes.
$candidates = @(Get-Disk | Where-Object {
	$_.BusType -eq "USB" -and $_.Size -gt 20GB -and $_.Size -lt 40GB -and $_.PartitionStyle -eq "GPT"
} | Where-Object {
	$disk = $_
	$labels = @(Get-Partition -DiskNumber $disk.Number -ErrorAction SilentlyContinue |
		Get-Volume -ErrorAction SilentlyContinue | ForEach-Object { $_.FileSystemLabel })
	($labels -contains "EFIESP") -or ($labels -contains "MainOS")
})

if ($candidates.Count -ne 1) {
	Write-Output "Found $($candidates.Count) disks that look like a Lumia's eMMC, need exactly 1. Nothing read."
	Write-Output "Is the phone in USB mass storage mode?"
	exit 2
}

$disk = $candidates[0]
$size = [int64]$disk.Size
Write-Output "eMMC: disk $($disk.Number), $($disk.FriendlyName), $size bytes"
if ($Check) { exit 0 }

if (-not $Out) { throw "-Out <folder> is required" }
$free = (Get-Item $Out.Substring(0, 3)).PSDrive.Free
if ($free -lt ($size + 1GB)) { throw "not enough free space on $($Out.Substring(0, 3))" }
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$image = Join-Path $Out "emmc-full.img"
if (Test-Path $image) { throw "$image already exists: not overwriting a backup" }
$log = Join-Path $Out "backup.log"

$GENERIC_READ = [uint32]2147483648
$handle = [ZtosRawDisk]::CreateFileW("\\.\PhysicalDrive$($disk.Number)", $GENERIC_READ, 3,
	[IntPtr]::Zero, 3, 0, [IntPtr]::Zero)
if ($handle.IsInvalid) {
	throw "cannot open the disk (error $([Runtime.InteropServices.Marshal]::GetLastWin32Error())): run as administrator"
}

$in = New-Object IO.FileStream($handle, [IO.FileAccess]::Read, 1, $false)
$part = "$image.part"
$outFile = [IO.File]::Open($part, [IO.FileMode]::Create, [IO.FileAccess]::Write)
$sha = [Security.Cryptography.SHA256]::Create()
$buffer = New-Object byte[] (4MB)
$done = [int64]0
$started = Get-Date
"started $started, disk $($disk.Number), $size bytes" | Set-Content $log
try {
	while ($done -lt $size) {
		$want = [int][Math]::Min([int64]$buffer.Length, $size - $done)
		$got = $in.Read($buffer, 0, $want)
		if ($got -le 0) { throw "read ended early at byte $done" }
		$outFile.Write($buffer, 0, $got)
		[void]$sha.TransformBlock($buffer, 0, $got, $null, 0)
		$done += $got
		if (($done % 1GB) -eq 0) {
			$line = "{0} GiB of {1:N1} GiB" -f ($done / 1GB), ($size / 1GB)
			Write-Output $line
			$line | Add-Content $log
		}
	}
	[void]$sha.TransformFinalBlock($buffer, 0, 0)
} finally {
	$outFile.Close()
	$in.Close()
}
$hash = -join ($sha.Hash | ForEach-Object { $_.ToString("x2") })
Move-Item $part $image
"$hash  emmc-full.img" | Set-Content (Join-Path $Out "emmc-full.img.sha256")
"finished $(Get-Date), $done bytes, sha256 $hash" | Add-Content $log
Write-Output "Done: $image, sha256 $hash"
