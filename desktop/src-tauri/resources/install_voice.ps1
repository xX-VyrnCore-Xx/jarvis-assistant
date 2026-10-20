# Installa la voce di JARVIS (XTTS v2) in una cartella dell'utente: Python portatile + librerie + modello (~3 GB in tutto).
param([Parameter(Mandatory = $true)][string]$Dir)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Force $Dir | Out-Null
$py = Join-Path $Dir 'python'
$exe = Join-Path $py 'python.exe'

function Run([string]$what, [scriptblock]$cmd) {
  & $cmd 2>&1 | ForEach-Object { Write-Output "$_" }
  if ($LASTEXITCODE -ne 0) { throw "$what non è riuscito (codice $LASTEXITCODE)" }
}

if (-not (Test-Path $exe)) {
  Write-Output 'STEP 1/4 Scarico Python…'
  $zip = Join-Path $Dir 'python.zip'
  Invoke-WebRequest 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile $zip
  Expand-Archive $zip -DestinationPath $py -Force
  Remove-Item $zip
  $pth = Get-ChildItem $py -Filter 'python3*._pth' | Select-Object -First 1
  (Get-Content $pth.FullName) -replace '^#\s*import site', 'import site' | Set-Content $pth.FullName
  $gp = Join-Path $Dir 'get-pip.py'
  Invoke-WebRequest 'https://bootstrap.pypa.io/get-pip.py' -OutFile $gp
  Run 'pip' { & $exe $gp --no-warn-script-location }
  Remove-Item $gp
}

Write-Output 'STEP 2/4 Scarico le librerie di sintesi vocale (alcuni minuti)…'
Run 'librerie' { & $exe -m pip install --no-warn-script-location --disable-pip-version-check 'torch==2.4.1' 'torchaudio==2.4.1' 'coqui-tts==0.24.3' 'transformers==4.44.2' 'numpy<2' 'fastapi==0.115.6' 'uvicorn==0.34.0' }

Write-Output 'STEP 3/4 Scarico il modello XTTS v2 (~1,8 GB)…'
$env:COQUI_TOS_AGREED = '1'
$env:TTS_HOME = Join-Path $Dir 'models'
Run 'modello' { & $exe -c "from TTS.utils.manage import ModelManager; ModelManager().download_model('tts_models/multilingual/multi-dataset/xtts_v2')" }

Set-Content (Join-Path $Dir 'ready') (Get-Date -Format o)
Write-Output 'STEP 4/4 Fatto.'
