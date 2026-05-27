@echo off
setlocal

set "ROOT_DIR=%~dp0.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"
set "DESKTOP=%USERPROFILE%\Desktop"
set "LAUNCHER=%DESKTOP%\US-Industry-Strength.cmd"

if not exist "%DESKTOP%" (
  echo 未找到桌面目录: %DESKTOP%
  exit /b 1
)

(
  echo @echo off
  echo cd /d "%ROOT_DIR%"
  echo call run.bat
) > "%LAUNCHER%"

echo 已创建桌面启动器:
echo   %LAUNCHER%
echo 以后双击它即可启动网站。

endlocal
