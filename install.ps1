$ErrorActionPreference = 'Stop'
$LobbyVersion = '1.5.2'
# The x64 build also runs under Windows on ARM's x64 emulation.
$LobbyAsset = "runlobby-$LobbyVersion-win32-x64.zip"
$LobbyBase = "https://github.com/blankmeta/runlobby/releases/download/v$LobbyVersion"
$LobbyTemp = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
$LobbyRoot = Join-Path $env:LOCALAPPDATA "Programs\RunLobby\$LobbyVersion"
New-Item -ItemType Directory -Force -Path $LobbyTemp | Out-Null
try {
    $Archive = Join-Path $LobbyTemp $LobbyAsset
    Invoke-WebRequest "$LobbyBase/$LobbyAsset" -UseBasicParsing -OutFile $Archive
    $ChecksumFile = Join-Path $LobbyTemp 'checksum.txt'
    Invoke-WebRequest "$LobbyBase/$LobbyAsset.sha256" -UseBasicParsing -OutFile $ChecksumFile
    $Expected = ((Get-Content $ChecksumFile -Raw).Trim() -split '\s+')[0]
    if ((Get-FileHash $Archive -Algorithm SHA256).Hash -ne $Expected) {
        throw 'Checksum mismatch. Nothing was installed.'
    }
    Expand-Archive $Archive -DestinationPath $LobbyTemp
    if (-not (Test-Path $LobbyRoot)) {
        New-Item -ItemType Directory -Force -Path (Split-Path $LobbyRoot) | Out-Null
        Move-Item (Join-Path $LobbyTemp 'runlobby') $LobbyRoot
    }
    $UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $Entries = @($UserPath -split ';' | Where-Object {
        $_ -and $_ -notlike "$env:LOCALAPPDATA\Programs\RunLobby\*" -and $_ -notlike "$env:LOCALAPPDATA\Programs\CodexLobby\*"
    })
    [Environment]::SetEnvironmentVariable('Path', ((@($LobbyRoot) + $Entries) -join ';'), 'User')
    $env:Path = "$LobbyRoot;$env:Path"
    & (Join-Path $LobbyRoot 'rlb.exe') --version
    Write-Host 'Installed. Run: rlb'
} finally {
    Remove-Item $LobbyTemp -Recurse -Force -ErrorAction SilentlyContinue
}
