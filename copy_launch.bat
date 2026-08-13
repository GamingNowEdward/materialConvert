@echo off
set "P=%~dp0launch.py"
set "CMD=__file__ = r'%P%'; exec(compile(open(__file__).read(), __file__, 'exec'))"
<nul set /p "=%CMD%" | clip
echo Launch command copied to clipboard!
echo.
echo %CMD%
echo.
pause
