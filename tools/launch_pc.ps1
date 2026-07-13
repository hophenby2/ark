param(
    [string]$GamePath = "E:\Hypergryph Launcher\games\Arknights\Arknights.exe",
    [string]$MitmDumpPath = $env:OPENDOCTORATE_MITMDUMP,
    [string]$MitmConfigDir = $env:OPENDOCTORATE_MITM_CONFIG,
    [int]$ServerPort = 8443,
    [int]$ProxyPort = 18080,
    [switch]$CheckOnly,
    [switch]$RestoreProxy
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$addonPath = Join-Path $PSScriptRoot "pc_proxy.py"
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$serverUrl = "http://127.0.0.1:$ServerPort"
$proxyAddress = "127.0.0.1:$ProxyPort"
$internetSettings = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
$stateDir = Join-Path $repoRoot ".runtime"
$proxyStatePath = Join-Path $stateDir "pc_proxy_state.json"
$proxyProcess = $null
$proxyStartedHere = $false
$proxyChanged = $false

Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class OpenDoctorateWinInet {
    [DllImport("wininet.dll", SetLastError = true)]
    public static extern bool InternetSetOption(
        IntPtr hInternet,
        int dwOption,
        IntPtr lpBuffer,
        int dwBufferLength
    );
}
"@

function Update-SystemProxy {
    [OpenDoctorateWinInet]::InternetSetOption([IntPtr]::Zero, 39, [IntPtr]::Zero, 0) | Out-Null
    [OpenDoctorateWinInet]::InternetSetOption([IntPtr]::Zero, 37, [IntPtr]::Zero, 0) | Out-Null
}

function Get-ProxyState {
    $settings = Get-ItemProperty -Path $internetSettings
    $names = $settings.PSObject.Properties.Name

    return [ordered]@{
        HadProxyEnable = $names -contains "ProxyEnable"
        ProxyEnable = if ($names -contains "ProxyEnable") { [int]$settings.ProxyEnable } else { 0 }
        HadProxyServer = $names -contains "ProxyServer"
        ProxyServer = if ($names -contains "ProxyServer") { [string]$settings.ProxyServer } else { "" }
        HadAutoConfigURL = $names -contains "AutoConfigURL"
        AutoConfigURL = if ($names -contains "AutoConfigURL") { [string]$settings.AutoConfigURL } else { "" }
    }
}

function Restore-ProxyState {
    param([Parameter(Mandatory = $true)]$State)

    if ($State.HadProxyEnable) {
        Set-ItemProperty -Path $internetSettings -Name "ProxyEnable" -Type DWord -Value ([int]$State.ProxyEnable)
    } else {
        Remove-ItemProperty -Path $internetSettings -Name "ProxyEnable" -ErrorAction SilentlyContinue
    }

    if ($State.HadProxyServer) {
        Set-ItemProperty -Path $internetSettings -Name "ProxyServer" -Type String -Value ([string]$State.ProxyServer)
    } else {
        Remove-ItemProperty -Path $internetSettings -Name "ProxyServer" -ErrorAction SilentlyContinue
    }

    if ($State.HadAutoConfigURL) {
        Set-ItemProperty -Path $internetSettings -Name "AutoConfigURL" -Type String -Value ([string]$State.AutoConfigURL)
    } else {
        Remove-ItemProperty -Path $internetSettings -Name "AutoConfigURL" -ErrorAction SilentlyContinue
    }

    Update-SystemProxy
}

function Enable-LocalProxy {
    Set-ItemProperty -Path $internetSettings -Name "ProxyEnable" -Type DWord -Value 1
    Set-ItemProperty -Path $internetSettings -Name "ProxyServer" -Type String -Value $proxyAddress
    Set-ItemProperty -Path $internetSettings -Name "AutoConfigURL" -Type String -Value ""
    Update-SystemProxy
}

function Test-HttpEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 3
    )

    try {
        $request = [System.Net.HttpWebRequest]::Create($Url)
        $request.Proxy = $null
        $request.Timeout = $TimeoutSeconds * 1000
        $request.ReadWriteTimeout = $TimeoutSeconds * 1000
        $response = $request.GetResponse()
        $statusCode = [int]$response.StatusCode
        $response.Close()
        return $statusCode -ge 200 -and $statusCode -lt 500
    } catch {
        return $false
    }
}

function Wait-ForEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 90
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpEndpoint -Url $Url) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Get-ListeningProcess {
    param([Parameter(Mandatory = $true)][int]$Port)

    $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $connection) {
        return $null
    }
    return Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
}

function Resolve-MitmDump {
    if (-not [string]::IsNullOrWhiteSpace($MitmDumpPath)) {
        if (-not (Test-Path -LiteralPath $MitmDumpPath -PathType Leaf)) {
            throw "mitmdump was not found at: $MitmDumpPath"
        }
        return (Resolve-Path -LiteralPath $MitmDumpPath).Path
    }

    $venvMitmDump = Join-Path $repoRoot ".venv\Scripts\mitmdump.exe"
    if (Test-Path -LiteralPath $venvMitmDump -PathType Leaf) {
        return $venvMitmDump
    }

    $command = Get-Command "mitmdump.exe" -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $referenceMitmDump = Get-Item -Path "E:\Arknights\*\Arknights\Server\ProxyServer\mitmdump.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -ne $referenceMitmDump) {
        return $referenceMitmDump.FullName
    }

    throw "mitmdump.exe was not found. Set OPENDOCTORATE_MITMDUMP or pass -MitmDumpPath."
}

function Test-MitMRootCertificate {
    param([Parameter(Mandatory = $true)][string]$ConfigDirectory)

    $certificatePath = Join-Path $ConfigDirectory "mitmproxy-ca-cert.cer"
    if (-not (Test-Path -LiteralPath $certificatePath -PathType Leaf)) {
        throw "The mitmproxy CA certificate was not generated at: $certificatePath"
    }

    $certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($certificatePath)
    $trusted = Get-ChildItem Cert:\CurrentUser\Root, Cert:\LocalMachine\Root -ErrorAction SilentlyContinue |
        Where-Object { $_.Thumbprint -eq $certificate.Thumbprint } |
        Select-Object -First 1

    if ($null -eq $trusted) {
        Write-Host "Installing the mitmproxy CA in the current user's trusted roots..."
        Import-Certificate -FilePath $certificatePath -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
    }
}

if ($RestoreProxy) {
    if (-not (Test-Path -LiteralPath $proxyStatePath -PathType Leaf)) {
        Write-Host "No saved proxy state was found."
        exit 0
    }

    $savedState = Get-Content -LiteralPath $proxyStatePath -Raw | ConvertFrom-Json
    Restore-ProxyState -State $savedState
    Remove-Item -LiteralPath $proxyStatePath -Force
    Write-Host "The saved system proxy settings were restored."
    exit 0
}

if (-not (Test-Path -LiteralPath $GamePath -PathType Leaf)) {
    throw "Arknights.exe was not found at: $GamePath"
}
if ($null -ne (Get-Process -Name "Arknights" -ErrorAction SilentlyContinue)) {
    throw "Arknights is already running. Close it before using this launcher."
}
if (-not (Test-Path -LiteralPath $addonPath -PathType Leaf)) {
    throw "The mitmproxy addon was not found at: $addonPath"
}
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "data\excel") -PathType Container)) {
    throw "data\excel is missing. Create the GameData junction before launching the server."
}

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

if (Test-Path -LiteralPath $proxyStatePath -PathType Leaf) {
    Write-Warning "A previous run left saved proxy settings. Restoring them before continuing."
    $staleState = Get-Content -LiteralPath $proxyStatePath -Raw | ConvertFrom-Json
    Restore-ProxyState -State $staleState
    Remove-Item -LiteralPath $proxyStatePath -Force
}

try {
    if (-not (Test-HttpEndpoint -Url "$serverUrl/config/prod/official/Windows/version")) {
        if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
            throw "The virtual environment is missing at: $pythonPath"
        }

        Write-Host "Starting OpenDoctorate on $serverUrl..."
        $oldNoProxy = $env:NO_PROXY
        $oldNoProxyLower = $env:no_proxy
        $env:NO_PROXY = ".hypergryph.com,.hycdn.cn,127.0.0.1,localhost"
        $env:no_proxy = $env:NO_PROXY
        try {
            Start-Process -FilePath $pythonPath `
                -ArgumentList "server\app.py" `
                -WorkingDirectory $repoRoot `
                -RedirectStandardOutput (Join-Path $stateDir "server.log") `
                -RedirectStandardError (Join-Path $stateDir "server-error.log") `
                -WindowStyle Hidden | Out-Null
        } finally {
            $env:NO_PROXY = $oldNoProxy
            $env:no_proxy = $oldNoProxyLower
        }

        if (-not (Wait-ForEndpoint -Url "$serverUrl/config/prod/official/Windows/version")) {
            throw "OpenDoctorate did not become ready. See .runtime\server-error.log."
        }
    }
    Write-Host "OpenDoctorate is ready at $serverUrl."

    $proxyProcess = Get-ListeningProcess -Port $ProxyPort
    if ($null -eq $proxyProcess) {
        $resolvedMitmDump = Resolve-MitmDump
        if ([string]::IsNullOrWhiteSpace($MitmConfigDir)) {
            $MitmConfigDir = Join-Path (Split-Path -Parent $resolvedMitmDump) "proxy_config"
        }
        New-Item -ItemType Directory -Path $MitmConfigDir -Force | Out-Null

        Write-Host "Starting the PC redirect proxy at http://$proxyAddress..."
        $mitmArguments = "--listen-host 127.0.0.1 --listen-port $ProxyPort --scripts `"$addonPath`" --set `"confdir=$MitmConfigDir`" --set flow_detail=1"
        $proxyProcess = Start-Process -FilePath $resolvedMitmDump `
            -ArgumentList $mitmArguments `
            -WorkingDirectory (Split-Path -Parent $resolvedMitmDump) `
            -RedirectStandardOutput (Join-Path $stateDir "mitmdump.log") `
            -RedirectStandardError (Join-Path $stateDir "mitmdump-error.log") `
            -WindowStyle Hidden `
            -PassThru
        $proxyStartedHere = $true

        $deadline = (Get-Date).AddSeconds(20)
        while ($null -eq (Get-ListeningProcess -Port $ProxyPort) -and (Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 250
        }
        if ($null -eq (Get-ListeningProcess -Port $ProxyPort)) {
            throw "mitmdump did not start. See .runtime\mitmdump-error.log."
        }
    } else {
        if ($proxyProcess.ProcessName -notlike "mitmdump*") {
            throw "Port $ProxyPort is already owned by $($proxyProcess.ProcessName) (PID $($proxyProcess.Id))."
        }

        if ([string]::IsNullOrWhiteSpace($MitmConfigDir)) {
            $MitmConfigDir = Join-Path (Split-Path -Parent $proxyProcess.Path) "proxy_config"
        }
        Write-Host "Reusing mitmdump PID $($proxyProcess.Id) on port $ProxyPort."
    }

    Test-MitMRootCertificate -ConfigDirectory $MitmConfigDir

    $testCode = & curl.exe -sS --ssl-no-revoke --proxy "http://$proxyAddress" `
        -o NUL -w "%{http_code}" `
        "https://ak-conf.hypergryph.com/config/prod/official/Windows/version"
    if ($LASTEXITCODE -ne 0 -or $testCode -ne "200") {
        throw "The redirect proxy health check failed with HTTP $testCode."
    }
    Write-Host "PC redirect proxy health check passed."

    if ($CheckOnly) {
        Write-Host "Check-only mode completed; the game was not started."
        exit 0
    }

    $originalProxyState = Get-ProxyState
    $originalProxyState | ConvertTo-Json | Set-Content -LiteralPath $proxyStatePath -Encoding ASCII
    $proxyChanged = $true
    Enable-LocalProxy
    Write-Host "System proxy changed from '$($originalProxyState.ProxyServer)' to '$proxyAddress'."

    $game = Start-Process -FilePath $GamePath -WorkingDirectory (Split-Path -Parent $GamePath) -PassThru
    Write-Host "Arknights started as PID $($game.Id). Close the game to restore the previous proxy."

    while (-not $game.HasExited) {
        Start-Sleep -Seconds 2
        $game.Refresh()

        $activeProxy = Get-ItemProperty -Path $internetSettings
        if ([int]$activeProxy.ProxyEnable -ne 1 -or [string]$activeProxy.ProxyServer -ne $proxyAddress) {
            Write-Warning "Another application changed the system proxy; applying the game proxy again."
            Enable-LocalProxy
        }
    }
} finally {
    if ($proxyChanged -and (Test-Path -LiteralPath $proxyStatePath -PathType Leaf)) {
        $savedState = Get-Content -LiteralPath $proxyStatePath -Raw | ConvertFrom-Json
        Restore-ProxyState -State $savedState
        Remove-Item -LiteralPath $proxyStatePath -Force
        Write-Host "The previous system proxy settings were restored."
    }

    if ($proxyStartedHere -and $null -ne $proxyProcess -and -not $proxyProcess.HasExited) {
        Stop-Process -Id $proxyProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
