Dim WshShell, scriptDir
Set WshShell = CreateObject("WScript.Shell")

' Get the folder this .vbs file lives in
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

' Run python in that folder, hidden window, don't wait
WshShell.Run "cmd /c cd /d """ & scriptDir & """ && python screenreader.py", 0, False
