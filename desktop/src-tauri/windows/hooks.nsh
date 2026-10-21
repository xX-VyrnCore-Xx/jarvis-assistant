; Ganci dell'installer NSIS: prima di installare, aggiornare o disinstallare si chiude JARVIS (con la voce e i processi figli),
; altrimenti i file in uso non si possono sostituire e resterebbe un processo in memoria.
!macro NSIS_HOOK_PREINSTALL
  nsExec::Exec 'taskkill /F /T /IM jarvis-desktop.exe'
  Sleep 800
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::Exec 'taskkill /F /T /IM jarvis-desktop.exe'
  Sleep 800
!macroend
