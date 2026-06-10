@echo off
setlocal EnableExtensions

rem Run the course-provided test entrypoint with the local Loma environment.

set "LOMA_ROOT=%~dp0"
if "%LOMA_ROOT:~-1%"=="\" set "LOMA_ROOT=%LOMA_ROOT:~0,-1%"

call "%LOMA_ROOT%\loma_env.cmd"
if errorlevel 1 exit /b %errorlevel%

pushd "%LOMA_ROOT%\tests"
python test.py
set "TEST_STATUS=%errorlevel%"
popd

exit /b %TEST_STATUS%
