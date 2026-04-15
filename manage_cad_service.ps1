# CAD System Service Management Script
# Run as Administrator for full functionality

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("install", "uninstall", "start", "stop", "restart", "status", "logs")]
    [string]$Action
)

$ServiceName = "FDDCADSystem"
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = (Get-Command python).Source

function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    } else {
        $input | Write-Output
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Install-Service {
    Write-ColorOutput Green "Installing CAD System Service..."
    
    if (-not (Test-Administrator)) {
        Write-ColorOutput Red "This action requires Administrator privileges. Please run PowerShell as Administrator."
        return
    }
    
    try {
        # Install pywin32 if not already installed
        Write-ColorOutput Yellow "Checking for pywin32..."
        $pywin32 = python -c "import win32serviceutil" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-ColorOutput Yellow "Installing pywin32..."
            pip install pywin32
        }
        
        # Install the service
        python "$ScriptPath\cad_service_wrapper.py" install
        
        Write-ColorOutput Green "Service installed successfully!"
        Write-ColorOutput Yellow "To start the service, run: .\manage_cad_service.ps1 start"
    }
    catch {
        Write-ColorOutput Red "Error installing service: $_"
    }
}

function Uninstall-Service {
    Write-ColorOutput Yellow "Uninstalling CAD System Service..."
    
    if (-not (Test-Administrator)) {
        Write-ColorOutput Red "This action requires Administrator privileges. Please run PowerShell as Administrator."
        return
    }
    
    try {
        # Stop service first if running
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service -and $service.Status -eq "Running") {
            Write-ColorOutput Yellow "Stopping service first..."
            Stop-Service -Name $ServiceName -Force
            Start-Sleep -Seconds 3
        }
        
        python "$ScriptPath\cad_service_wrapper.py" uninstall
        Write-ColorOutput Green "Service uninstalled successfully!"
    }
    catch {
        Write-ColorOutput Red "Error uninstalling service: $_"
    }
}

function Start-Service {
    Write-ColorOutput Green "Starting CAD System Service..."
    
    if (-not (Test-Administrator)) {
        Write-ColorOutput Red "This action requires Administrator privileges. Please run PowerShell as Administrator."
        return
    }
    
    try {
        python "$ScriptPath\cad_service_wrapper.py" start
        Start-Sleep -Seconds 2
        
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service -and $service.Status -eq "Running") {
            Write-ColorOutput Green "Service started successfully!"
            Write-ColorOutput Yellow "CAD System is now running at: http://127.0.0.1:5000"
        } else {
            Write-ColorOutput Red "Service failed to start. Check logs for details."
        }
    }
    catch {
        Write-ColorOutput Red "Error starting service: $_"
    }
}

function Stop-Service {
    Write-ColorOutput Yellow "Stopping CAD System Service..."
    
    if (-not (Test-Administrator)) {
        Write-ColorOutput Red "This action requires Administrator privileges. Please run PowerShell as Administrator."
        return
    }
    
    try {
        python "$ScriptPath\cad_service_wrapper.py" stop
        Start-Sleep -Seconds 2
        
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if (-not $service -or $service.Status -eq "Stopped") {
            Write-ColorOutput Green "Service stopped successfully!"
        } else {
            Write-ColorOutput Red "Service may still be running. Check status."
        }
    }
    catch {
        Write-ColorOutput Red "Error stopping service: $_"
    }
}

function Restart-Service {
    Write-ColorOutput Yellow "Restarting CAD System Service..."
    Stop-Service
    Start-Sleep -Seconds 3
    Start-Service
}

function Get-ServiceStatus {
    Write-ColorOutput Cyan "CAD System Service Status:"
    Write-Output ""
    
    try {
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service) {
            $status = $service.Status
            $startType = $service.StartType
            
            Write-ColorOutput White "Service Name: $($service.Name)"
            Write-ColorOutput White "Display Name: $($service.DisplayName)"
            Write-ColorOutput White "Status: " -NoNewline
            
            switch ($status) {
                "Running" { Write-ColorOutput Green $status }
                "Stopped" { Write-ColorOutput Red $status }
                "Starting" { Write-ColorOutput Yellow $status }
                "Stopping" { Write-ColorOutput Yellow $status }
                default { Write-ColorOutput White $status }
            }
            
            Write-ColorOutput White "Start Type: $startType"
            
            # Check if web interface is responding
            try {
                $response = Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/status" -UseBasicParsing -TimeoutSec 5
                if ($response.StatusCode -eq 200) {
                    Write-ColorOutput Green "Web Interface: Online (http://127.0.0.1:5000)"
                } else {
                    Write-ColorOutput Red "Web Interface: Offline (HTTP $($response.StatusCode))"
                }
            }
            catch {
                Write-ColorOutput Red "Web Interface: Offline (Connection failed)"
            }
        } else {
            Write-ColorOutput Red "Service not found. Run 'install' to install the service."
        }
    }
    catch {
        Write-ColorOutput Red "Error checking service status: $_"
    }
}

function Show-Logs {
    Write-ColorOutput Cyan "CAD System Logs:"
    Write-Output ""
    
    $logFile = "$ScriptPath\cad_monitor.log"
    if (Test-Path $logFile) {
        Write-ColorOutput Yellow "Last 20 log entries:"
        Write-Output ""
        Get-Content $logFile -Tail 20 | ForEach-Object {
            if ($_ -match "ERROR") {
                Write-ColorOutput Red $_
            } elseif ($_ -match "WARNING") {
                Write-ColorOutput Yellow $_
            } elseif ($_ -match "INFO") {
                Write-ColorOutput Green $_
            } else {
                Write-Output $_
            }
        }
    } else {
        Write-ColorOutput Yellow "No log file found at: $logFile"
    }
}

# Main execution
switch ($Action) {
    "install" { Install-Service }
    "uninstall" { Uninstall-Service }
    "start" { Start-Service }
    "stop" { Stop-Service }
    "restart" { Restart-Service }
    "status" { Get-ServiceStatus }
    "logs" { Show-Logs }
}

Write-Output ""
Write-ColorOutput Cyan "Available commands:"
Write-ColorOutput White "  .\manage_cad_service.ps1 install   - Install the service"
Write-ColorOutput White "  .\manage_cad_service.ps1 uninstall - Remove the service"
Write-ColorOutput White "  .\manage_cad_service.ps1 start     - Start the service"
Write-ColorOutput White "  .\manage_cad_service.ps1 stop      - Stop the service"
Write-ColorOutput White "  .\manage_cad_service.ps1 restart   - Restart the service"
Write-ColorOutput White "  .\manage_cad_service.ps1 status    - Check service status"
Write-ColorOutput White "  .\manage_cad_service.ps1 logs      - View recent logs"
