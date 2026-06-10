@echo off
setlocal EnableExtensions

rem Configure the Loma course environment for this repository.
rem This script is meant to be called from cmd.exe or from PowerShell via:
rem   cmd.exe /s /c "call loma_env.cmd && <command>"

set "LOMA_ROOT=%~dp0"
if "%LOMA_ROOT:~-1%"=="\" set "LOMA_ROOT=%LOMA_ROOT:~0,-1%"

set "VENV_SCRIPTS=%LOMA_ROOT%\.venv312\Scripts"
if not exist "%VENV_SCRIPTS%\python.exe" (
    echo [ERROR] Could not find Python at "%VENV_SCRIPTS%\python.exe".
    exit /b 1
)

set "ISPC_BIN=%LOMA_ROOT%\tools\ispc\ispc-v1.30.0-windows\bin"
if not exist "%ISPC_BIN%\ispc.exe" (
    echo [ERROR] Could not find ISPC at "%ISPC_BIN%\ispc.exe".
    exit /b 1
)

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set "VCVARS64="
if exist "%VSWHERE%" (
    for /f "usebackq tokens=*" %%I in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do (
        set "VCVARS64=%%I\VC\Auxiliary\Build\vcvars64.bat"
    )
)

if not defined VCVARS64 (
    for %%I in (
        "%ProgramFiles(x86)%\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
        "%ProgramFiles%\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
        "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
        "%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
    ) do (
        if exist "%%~I" set "VCVARS64=%%~I"
    )
)

if not exist "%VCVARS64%" (
    echo [ERROR] Could not find MSVC vcvars64.bat.
    exit /b 1
)

call "%VCVARS64%" >nul
set "PATH=%VENV_SCRIPTS%;%ISPC_BIN%;%PATH%"

echo Loma environment ready.
python --version
where cl
where link
where ispc

endlocal & (
    set "PATH=%PATH%"
    set "INCLUDE=%INCLUDE%"
    set "LIB=%LIB%"
    set "LIBPATH=%LIBPATH%"
    set "VSCMD_ARG_TGT_ARCH=%VSCMD_ARG_TGT_ARCH%"
    set "VSCMD_ARG_HOST_ARCH=%VSCMD_ARG_HOST_ARCH%"
    set "VCToolsInstallDir=%VCToolsInstallDir%"
    set "VCINSTALLDIR=%VCINSTALLDIR%"
    set "VSINSTALLDIR=%VSINSTALLDIR%"
    set "WindowsSdkDir=%WindowsSdkDir%"
    set "WindowsSDKLibVersion=%WindowsSDKLibVersion%"
    set "WindowsSDKVersion=%WindowsSDKVersion%"
)
