@echo off
setlocal enabledelayedexpansion
for %%p in (python3 python py) do (
  for %%e in (.exe .bat .cmd) do (
    set "PYCAND=%%p%%e"
    for %%f in ("!PYCAND!") do (
      if not "%%~$PATH:f"=="" (
        if /i "%%p"=="py" (
          "%%~$PATH:f" -3 %*
        ) else (
          "%%~$PATH:f" %*
        )
        exit /b !ERRORLEVEL!
      )
    )
  )
)
>&2 echo python not found (tried: python3, python, py)
exit /b 2
