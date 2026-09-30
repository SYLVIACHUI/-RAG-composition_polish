$ErrorActionPreference = 'Stop'
$downloadDir = Join-Path $PSScriptRoot '.local\downloads'
$installer = Join-Path $downloadDir 'OllamaSetup.exe'
$assembledInstaller = Join-Path $downloadDir 'OllamaSetup-complete.exe'
if (Test-Path $assembledInstaller) { $installer = $assembledInstaller }
$installDir = 'D:\Ollama'
$modelDir = 'D:\Ollama\models'
$ollamaExe = Join-Path $installDir 'ollama.exe'

if (-not (Test-Path $ollamaExe)) {
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|, )O=Ollama Inc\.(,|$)') {
        throw 'The official Ollama installer must be fully downloaded and have a valid Ollama Inc. signature.'
    }
    New-Item -ItemType Directory -Path $modelDir -Force | Out-Null
    [Environment]::SetEnvironmentVariable('OLLAMA_MODELS', $modelDir, 'User')
    $env:OLLAMA_MODELS = $modelDir
    $markerDir = Join-Path $env:LOCALAPPDATA 'Ollama'
    New-Item -ItemType Directory -Path $markerDir -Force | Out-Null
    New-Item -ItemType File -Path (Join-Path $markerDir 'upgraded') -Force | Out-Null
    $installProcess = Start-Process -FilePath $installer -ArgumentList '/VERYSILENT /NORESTART /SUPPRESSMSGBOXES /DIR="D:\Ollama"' -WindowStyle Hidden -PassThru
    $installProcess.WaitForExit()
    if ($installProcess.ExitCode -ne 0) { throw "Installer exit code: $($installProcess.ExitCode)" }
}

$env:OLLAMA_MODELS = $modelDir
try {
    Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 5 | Out-Null
} catch {
    Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden -RedirectStandardOutput (Join-Path $downloadDir 'server.stdout.log') -RedirectStandardError (Join-Path $downloadDir 'server.stderr.log') | Out-Null
}
$ready = $false
foreach ($attempt in 1..30) {
    try {
        $version = Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 5
        $ready = $true
        break
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $ready) { throw 'Ollama did not start.' }
Write-Output "Ollama version: $($version.version)"

foreach ($model in @('qwen3:4b', 'qwen3-embedding:0.6b')) {
    $safeName = $model.Replace(':', '-')
    $bodyFile = Join-Path $downloadDir "$safeName-request.json"
    @{ model = $model; stream = $true } | ConvertTo-Json -Compress | Set-Content -LiteralPath $bodyFile -Encoding utf8
    $logFile = Join-Path $downloadDir "$safeName-pull.jsonl"
    Write-Output "Downloading $model"
    & curl.exe --fail --silent --show-error --no-buffer --header 'Content-Type: application/json' --data-binary "@$bodyFile" http://127.0.0.1:11434/api/pull --output $logFile
    if ($LASTEXITCODE -ne 0) { throw "Download request failed: $model" }
    $lastResult = Get-Content -LiteralPath $logFile -Tail 1 | ConvertFrom-Json
    if ($lastResult.status -ne 'success') { throw "Model download failed: $($lastResult | ConvertTo-Json -Compress)" }
    Write-Output "Downloaded $model"
}

$embeddingBody = @{ model = 'qwen3-embedding:0.6b'; input = 'This is a local embedding test.'; keep_alive = 0 } | ConvertTo-Json
$embedding = Invoke-RestMethod http://127.0.0.1:11434/api/embed -Method Post -ContentType 'application/json' -Body $embeddingBody -TimeoutSec 180
if ($embedding.embeddings.Count -ne 1 -or $embedding.embeddings[0].Count -eq 0) { throw 'Embedding test failed.' }
$chatBody = @{ model = 'qwen3:4b'; messages = @(@{ role = 'user'; content = 'Say hello in one sentence.' }); think = $true; stream = $false; keep_alive = 0; options = @{ num_ctx = 4096; num_predict = 1024 } } | ConvertTo-Json -Depth 6
$chat = Invoke-RestMethod http://127.0.0.1:11434/api/chat -Method Post -ContentType 'application/json' -Body $chatBody -TimeoutSec 180
if (-not $chat.done -or $chat.done_reason -ne 'stop' -or -not $chat.message.content) { throw 'Chat did not produce a complete answer.' }
$result = @{ version = $version.version; chat_model = 'qwen3:4b'; embedding_model = 'qwen3-embedding:0.6b'; embedding_dimensions = $embedding.embeddings[0].Count; chat_response = $chat.message.content; tested_at = (Get-Date).ToString('o'); model_directory = $modelDir }
$result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'ollama-verification.json') -Encoding utf8
$result | ConvertTo-Json
