$ErrorActionPreference = "Stop"

python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name MagicalLayers `
  --hidden-import win32com.client `
  --hidden-import pythoncom `
  --hidden-import pywintypes `
  --hidden-import winocr `
  --collect-submodules winocr `
  --collect-submodules winrt `
  desktop_launcher.py

Write-Host "Built dist\MagicalLayers\MagicalLayers.exe"
