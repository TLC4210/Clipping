# Creates the three daily Task Scheduler jobs (folder \Clipper\) for THIS copy of the repo.
# Run once from PowerShell:  powershell -ExecutionPolicy Bypass -File scripts\install-schedule.ps1
# Re-running replaces the jobs. Remove them with:  scripts\install-schedule.ps1 -Remove
#
#   03:00  Daily winners research   competitor research + trending-music report   (max 2 h)
#   04:00  Daily clip making        fetch, edit and render clips for review        (max 3 h)
#   08:00  Daily analytics check    channel stats report                           (max 30 min)
#
# Jobs run as you, only while you're logged in, wake the PC from sleep, and catch up if the PC was
# off at the scheduled time. Nothing is ever posted by these jobs: you approve and publish.
param([switch]$Remove)

$repo = Split-Path -Parent $PSScriptRoot
$path = "\Clipper\"
$jobs = @(
    @{ Name = "Daily winners research"; Script = "daily-winners.cmd";   At = "03:00"; Limit = (New-TimeSpan -Hours 2) },
    @{ Name = "Daily clip making";      Script = "daily-clips.cmd";     At = "04:00"; Limit = (New-TimeSpan -Hours 3) },
    @{ Name = "Daily analytics check";  Script = "daily-analytics.cmd"; At = "08:00"; Limit = (New-TimeSpan -Minutes 30) }
)

foreach ($j in $jobs) {
    Unregister-ScheduledTask -TaskPath $path -TaskName $j.Name -Confirm:$false -ErrorAction SilentlyContinue
    if ($Remove) { Write-Host "Removed $($j.Name)"; continue }
    $action = New-ScheduledTaskAction -Execute (Join-Path $repo "scripts\$($j.Script)") -WorkingDirectory $repo
    $trigger = New-ScheduledTaskTrigger -Daily -At $j.At
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit $j.Limit -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
    Register-ScheduledTask -TaskPath $path -TaskName $j.Name -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal | Out-Null
    Write-Host "Scheduled $($j.Name) daily at $($j.At)"
}
if (-not $Remove) { Write-Host "Logs go to $repo\data\logs. Test one now: Start-ScheduledTask -TaskPath '\Clipper\' -TaskName 'Daily analytics check'" }
