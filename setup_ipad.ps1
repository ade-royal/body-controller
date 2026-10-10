# Start the prepared xtool signing/install flow. Credentials are entered locally.
param([switch]$Check, [switch]$Resume, [switch]$DeviceKit, [switch]$Fast)

$ErrorActionPreference = 'Stop'
$taskPathOutput = & wsl.exe -d Ubuntu --exec wslpath -u $PSScriptRoot
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($taskPathOutput)) {
    throw 'Could not access the project from Ubuntu.'
}
$taskLinuxRoot = ([string]$taskPathOutput).Trim()
if ($DeviceKit -and $Fast) { throw 'Choose either -DeviceKit or -Fast.' }
$taskHelperName = if ($Fast) { 'install-fast-devicekit.sh' }
elseif ($DeviceKit) { 'install-devicekit.sh' }
else { 'xtool-helper.sh' }
$taskHelper = $taskLinuxRoot + '/.ios-tools/' + $taskHelperName
$taskHelperArgs = @($taskHelper)
if ($Check) { $taskHelperArgs += '--check' }
elseif ($Resume) { $taskHelperArgs += '--resume' }
& wsl.exe -d Ubuntu --exec bash @taskHelperArgs
if ($LASTEXITCODE -ne 0) { throw 'xtool did not confirm successful helper installation.' }
