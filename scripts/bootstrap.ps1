$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Set-Location (Split-Path $PSScriptRoot -Parent)
$architecture = [Environment]::GetEnvironmentVariable('PROCESSOR_ARCHITEW6432')
if (!$architecture) { $architecture = $env:PROCESSOR_ARCHITECTURE }
if ($architecture -ne 'AMD64') { throw 'Jarvis currently supports Windows x64 only. Windows ARM is not yet validated.' }
if ([Environment]::OSVersion.Version.Build -lt 19045) { throw 'Jarvis requires Windows 10 22H2 or Windows 11.' }
New-Item -ItemType Directory -Force '.runtime\uv', '.cache\downloads' | Out-Null
$uv = Join-Path (Get-Location) '.runtime\uv\uv.exe'
$sha = 'b27eb789f281e398a82197477de727fc8faf08605152115686da2c3cba0d25f7'
if (!(Test-Path $uv) -or !((& $uv --version) -match '^uv 0.10.6')) {
    $archive = Join-Path (Get-Location) '.cache\downloads\uv-windows-x64.zip'
    if (!(Test-Path $archive) -or (Get-FileHash $archive -Algorithm SHA256).Hash.ToLower() -ne $sha) {
        Write-Host 'Installing the pinned Jarvis bootstrap runtime...'
        $downloaded = $false
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            try {
                Invoke-WebRequest -UseBasicParsing 'https://github.com/astral-sh/uv/releases/download/0.10.6/uv-x86_64-pc-windows-msvc.zip' -OutFile "$archive.part"
                if ((Get-FileHash "$archive.part" -Algorithm SHA256).Hash.ToLower() -ne $sha) { throw 'UV checksum mismatch.' }
                Move-Item -Force "$archive.part" $archive
                $downloaded = $true
                break
            } catch { if ($attempt -eq 3) { throw }; Start-Sleep -Seconds $attempt }
        }
        if (!$downloaded) { throw 'UV download failed.' }
    }
    Expand-Archive -Force $archive '.runtime\uv'
}
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.runtime\python'
$env:UV_PYTHON_BIN_DIR = Join-Path (Get-Location) '.runtime\bin'
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.cache\uv'
$env:JARVIS_UV = $uv
$env:UV_PYTHON_PREFERENCE = 'only-managed'
& $uv python install --no-bin --no-registry --install-dir $env:UV_PYTHON_INSTALL_DIR 3.11.14
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$bootstrapPython = & $uv python find --system 3.11.14
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $bootstrapPython scripts/manage.py @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
