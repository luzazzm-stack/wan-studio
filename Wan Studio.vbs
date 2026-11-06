' Starts the Wan Studio server in the background (if it isn't running) and opens the app window.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir

Function ServerUp()
  On Error Resume Next
  Set http = CreateObject("MSXML2.ServerXMLHTTP")
  http.setTimeouts 1000, 1000, 1000, 1000
  http.Open "GET", "http://127.0.0.1:8765/api/state", False
  http.Send
  ServerUp = (Err.Number = 0 And http.Status = 200)
End Function

If Not ServerUp() Then
  sh.Run """" & dir & "\.venv\Scripts\pythonw.exe"" """ & dir & "\server.py""", 0, False
  For i = 1 To 40
    WScript.Sleep 500
    If ServerUp() Then Exit For
  Next
End If

chrome = sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\Google\Chrome\Application\chrome.exe"
If fso.FileExists(chrome) Then
  sh.Run """" & chrome & """ --app=http://localhost:8765 --window-size=1400,900", 1, False
Else
  sh.Run "http://localhost:8765", 1, False
End If
