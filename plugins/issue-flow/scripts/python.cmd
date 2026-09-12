@echo off
rem Windows twin of python.sh: run the first of python3 / python / py -3 that exists.
rem Exit 2 when none is found (no implicit fallback), matching python.sh byte for byte.
rem
rem Comments are ASCII on purpose: cmd.exe parses .cmd in the OEM code page (cp932 on
rem Japanese Windows), so UTF-8 Japanese here corrupts the parse and spills comment
rem text into executable lines. Keep the Japanese rationale in SKILL.md, not here.
rem
rem CRITICAL: a plain ERRORLEVEL reference inside a for block is expanded at parse
rem time, so it freezes to the value from before the loop (normally 0). Returning
rem the child's exit code needs setlocal enabledelayedexpansion plus the delayed
rem form. Without it STALE and ERROR are both reported as exit=0, and the caller
rem misreads that as "read the diff" -- a worse failure than empty output (#38).
setlocal enabledelayedexpansion
rem The PATH-search modifier does not apply PATHEXT, so the extension has to be
rem part of the candidate name. .bat and .cmd are included because scoop and
rem conda ship their shims that way.
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
