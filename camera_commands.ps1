# Arkansas Camera System PowerShell Commands
# Run these commands in PowerShell

Write-Host "🚨 Arkansas Camera System Console Commands" -ForegroundColor Cyan
Write-Host "=" * 50 -ForegroundColor Cyan

# Function to test a single camera
function Test-Camera {
    param([int]$CameraId)
    
    $url = "https://actis.idrivearkansas.com/index.php/api/cameras/image?camera=$CameraId"
    Write-Host "🔍 Testing Camera $CameraId..." -ForegroundColor Yellow
    Write-Host "URL: $url" -ForegroundColor Gray
    
    try {
        $response = Invoke-WebRequest -Uri $url -TimeoutSec 10
        Write-Host "Status Code: $($response.StatusCode)" -ForegroundColor Green
        Write-Host "Content-Type: $($response.Headers['Content-Type'])" -ForegroundColor Green
        Write-Host "Content-Length: $($response.Content.Length) bytes" -ForegroundColor Green
        
        if ($response.StatusCode -eq 200) {
            $contentType = $response.Headers['Content-Type']
            if ($contentType -like "*image*") {
                Write-Host "✅ Camera is working!" -ForegroundColor Green
                return $true
            } else {
                Write-Host "❌ Not an image" -ForegroundColor Red
                return $false
            }
        } else {
            Write-Host "❌ HTTP Error: $($response.StatusCode)" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

# Function to get system data
function Get-SystemData {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:5000/api/camera-data"
        Write-Host "📊 System Data:" -ForegroundColor Cyan
        $response | ConvertTo-Json -Depth 3
    } catch {
        Write-Host "❌ Error getting system data: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# Function to send dispatch message
function Send-DispatchMessage {
    param(
        [string]$Message,
        [string]$Priority = "normal"
    )
    
    $data = @{
        message = $Message
        priority = $Priority
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:5000/api/send-dispatch" -Method POST -Body $data -ContentType "application/json"
        if ($response.success) {
            Write-Host "✅ Dispatch message sent successfully!" -ForegroundColor Green
        } else {
            Write-Host "❌ Failed to send message: $($response.error)" -ForegroundColor Red
        }
    } catch {
        Write-Host "❌ Error sending dispatch: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# Function to test multiple cameras
function Test-MultipleCameras {
    param(
        [int]$StartId,
        [int]$EndId
    )
    
    Write-Host "🔍 Testing cameras $StartId to $EndId..." -ForegroundColor Yellow
    $workingCameras = @()
    
    for ($i = $StartId; $i -le $EndId; $i++) {
        if (Test-Camera -CameraId $i) {
            $workingCameras += $i
        }
        Start-Sleep -Milliseconds 100
    }
    
    Write-Host "`n📊 Found $($workingCameras.Count) working cameras: $($workingCameras -join ', ')" -ForegroundColor Cyan
}

# Main menu
function Show-Menu {
    Write-Host "`nAvailable Commands:" -ForegroundColor Yellow
    Write-Host "1. Test single camera (e.g., 349)" -ForegroundColor White
    Write-Host "2. Test camera range (e.g., 300-400)" -ForegroundColor White
    Write-Host "3. Get system data (JSON)" -ForegroundColor White
    Write-Host "4. Send dispatch message" -ForegroundColor White
    Write-Host "5. Test known cameras (349, 350)" -ForegroundColor White
    Write-Host "6. Exit" -ForegroundColor White
}

# Main loop
do {
    Show-Menu
    $choice = Read-Host "`nEnter command (1-6)"
    
    switch ($choice) {
        "1" {
            $cameraId = Read-Host "Enter camera ID"
            if ($cameraId -match '^\d+$') {
                Test-Camera -CameraId [int]$cameraId
            } else {
                Write-Host "❌ Invalid camera ID" -ForegroundColor Red
            }
        }
        "2" {
            $start = Read-Host "Start camera ID"
            $end = Read-Host "End camera ID"
            if ($start -match '^\d+$' -and $end -match '^\d+$') {
                Test-MultipleCameras -StartId [int]$start -EndId [int]$end
            } else {
                Write-Host "❌ Invalid range" -ForegroundColor Red
            }
        }
        "3" {
            Get-SystemData
        }
        "4" {
            $message = Read-Host "Enter dispatch message"
            if ($message) {
                $priority = Read-Host "Priority (normal/medium/high)"
                if ($priority -notin @("normal", "medium", "high")) {
                    $priority = "normal"
                }
                Send-DispatchMessage -Message $message -Priority $priority
            } else {
                Write-Host "❌ Message cannot be empty" -ForegroundColor Red
            }
        }
        "5" {
            Write-Host "🔍 Testing known cameras..." -ForegroundColor Yellow
            Test-Camera -CameraId 349
            Write-Host ""
            Test-Camera -CameraId 350
        }
        "6" {
            Write-Host "👋 Goodbye!" -ForegroundColor Green
            break
        }
        default {
            Write-Host "❌ Invalid choice" -ForegroundColor Red
        }
    }
} while ($true)
