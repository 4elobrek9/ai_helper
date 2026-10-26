# Ollama Health Check Script
# Проверяет доступность Ollama на localhost:11434

try {
    $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags?verbose=false" -TimeoutSec 5 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Host "SUCCESS: Ollama запущен и доступен на http://localhost:11434" -ForegroundColor Green
        $body = $response.Content | ConvertFrom-Json
        if ($body.models) {
            Write-Host "Доступные модели:" -ForegroundColor Cyan
            foreach ($model in $body.models) {
                Write-Host "  - $($model.name)" -ForegroundColor Yellow
            }
        } else {
            Write-Host "! Модель не найдена в списке (попробуйте загрузить через Ollama UI)" -ForegroundColor DarkYellow
        }
        exit 0
    }
    else {
        Write-Host "ERROR: Ollama не отвечает (статус $($response.StatusCode))" -ForegroundColor Red
        exit 1
    }
}
catch {
    Write-Host "ERROR: Ollama недоступен или ошибка: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}