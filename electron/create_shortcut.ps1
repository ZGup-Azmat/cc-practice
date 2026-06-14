$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Tomato Timer.lnk')
$Shortcut.TargetPath = 'C:\Users\BHkx\Desktop\first-cc\electron\launcher.vbs'
$Shortcut.WorkingDirectory = 'C:\Users\BHkx\Desktop\first-cc\electron'
$Shortcut.IconLocation = 'C:\Users\BHkx\Desktop\first-cc\static\tomato.ico'
$Shortcut.Description = 'Tomato Timer - Pomodoro'
$Shortcut.Save()
Write-Output 'Desktop shortcut updated!'
