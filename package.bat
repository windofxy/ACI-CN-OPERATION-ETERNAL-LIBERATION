@echo off
setlocal enabledelayedexpansion
set "ROOT=%~dp0"
set "SEVENZIP=C:\Program Files\7-Zip\7z.exe"
set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "!ISCC!" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
for /f "tokens=3" %%V in ('findstr /b "#define AppVersion" "%~dp0OEL.iss"') do set "VERSION=%%~V"

echo ============================================================
echo  ACI-RPCS3 - Package builder
echo ============================================================
echo.

if not exist "!SEVENZIP!" (
    echo ERROR: 7-Zip not found at:
    echo   !SEVENZIP!
    echo.
    echo Install 7-Zip from https://www.7-zip.org/ then retry.
    pause & exit /b 1
)

if not exist "!ISCC!" (
    echo ERROR: Inno Setup 6 not found at:
    echo   !ISCC!
    echo.
    echo Install Inno Setup 6 from https://jrsoftware.org/isinfo.php then retry.
    pause & exit /b 1
)

echo Output: %ROOT%  (version !VERSION!)
echo.

:: 0. Provision embeddable Python so the installer can bundle it (no first-run
::    download for end users). Only runs when absent; needs internet once.
if not exist "%ROOT%BIN\_app\python\pythonw.exe" (
    echo [0/3] Provisioning embeddable Python...
    call "%ROOT%BIN\_app\setup.bat"
    if not exist "%ROOT%BIN\_app\python\pythonw.exe" (
        echo ERROR: Python provisioning failed. Cannot bundle it.
        pause & exit /b 1
    )
    echo Done.
    echo.
)

:: 0.5. Prune PySide6 build artifacts that are not needed at runtime.
::      Some wheels ship deep qml/Qt/*/objects-* trees containing .obj files;
::      on GitHub Actions their absolute paths can exceed Inno Setup's limit.
set "PYSIDE_QML=%ROOT%BIN\_app\python\Lib\site-packages\PySide6\qml\Qt"
if exist "!PYSIDE_QML!" (
    echo [0.5/3] Pruning PySide6 build artifacts...
    powershell -NoProfile -Command ^
        "$root = '%PYSIDE_QML%'; " ^
        "Get-ChildItem -Path $root -Directory -Recurse -Filter 'objects-*' -ErrorAction SilentlyContinue | " ^
        "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"
    echo Done.
    echo.
)

:: 1. Build installer
echo [1/3] Building installer...
"!ISCC!" "%ROOT%OEL.iss"
if errorlevel 1 (
    echo ERROR: InnoSetup compilation failed.
    pause & exit /b 1
)
echo Done.
echo.

:: 2. SRC archive
echo [2/3] Packaging SRC...
if exist "%ROOT%OEL-SRC-!VERSION!.7z" del "%ROOT%OEL-SRC-!VERSION!.7z"
"!SEVENZIP!" a -t7z -m0=lzma2 -mx=9 -mfb=64 -md=32m -ms=on ^
    "%ROOT%OEL-SRC-!VERSION!.7z" ^
    "%ROOT%SRC\README.md" ^
    "%ROOT%SRC\PATCH\" ^
    "%ROOT%SRC\apply-patches.bat" ^
    "%ROOT%SRC\apply-patches.sh" ^
    "%ROOT%SRC\clone-git-repos.bat" ^
    "%ROOT%SRC\clone-git-repos.sh" ^
    "%ROOT%SRC\reset-git-repos.bat" ^
    "%ROOT%SRC\reset-git-repos.sh" ^
    "%ROOT%SRC\pinned-commits.env"
if errorlevel 1 (
    echo ERROR: SRC packaging failed.
    pause & exit /b 1
)
echo Done.
echo.

:: 3. Docker source bundle (for Linux self-hosters)
echo [3/3] Bundling Docker source...
set "DSTAGE=%TEMP%\OEL-DOCKER-!VERSION!"
if exist "!DSTAGE!" rmdir /s /q "!DSTAGE!"
mkdir "!DSTAGE!\BIN\docker\gameserver"
mkdir "!DSTAGE!\BIN\docker\rpcn"
mkdir "!DSTAGE!\BIN\_app\gameserver"
mkdir "!DSTAGE!\BIN\_app\assets"
mkdir "!DSTAGE!\SRC\PATCH\RPCN"
copy /Y "%ROOT%BIN\docker-compose.yml"                    "!DSTAGE!\BIN\" >nul
copy /Y "%ROOT%BIN\docker\gameserver\Dockerfile"          "!DSTAGE!\BIN\docker\gameserver\" >nul
copy /Y "%ROOT%BIN\docker\rpcn\Dockerfile"                "!DSTAGE!\BIN\docker\rpcn\" >nul
copy /Y "%ROOT%BIN\docker\rpcn\entrypoint.sh"             "!DSTAGE!\BIN\docker\rpcn\" >nul
copy /Y "%ROOT%BIN\_app\gameserver\opeternal_listener.py" "!DSTAGE!\BIN\_app\gameserver\" >nul
copy /Y "%ROOT%BIN\_app\assets\ascii.txt"                 "!DSTAGE!\BIN\_app\assets\" >nul
copy /Y "%ROOT%SRC\PATCH\RPCN\tss-server.patch"           "!DSTAGE!\SRC\PATCH\RPCN\" >nul
copy /Y "%ROOT%BIN\docker\PACKAGE-README.md"              "!DSTAGE!\README.md" >nul

if exist "%ROOT%OEL-DOCKER-!VERSION!.7z" del "%ROOT%OEL-DOCKER-!VERSION!.7z"
pushd "%TEMP%"
"!SEVENZIP!" a -t7z -m0=lzma2 -mx=9 -mfb=64 -md=32m -ms=on ^
    "%ROOT%OEL-DOCKER-!VERSION!.7z" ^
    "OEL-DOCKER-!VERSION!\" >nul
popd
if errorlevel 1 (
    echo ERROR: Docker bundle packaging failed.
    pause & exit /b 1
)
rmdir /s /q "!DSTAGE!"
echo Done.
echo.

echo ============================================================
echo  Packaging complete:
echo    OP-ETERNAL-Setup-!VERSION!.exe  - installer for end users
echo    OEL-SRC-!VERSION!.7z            - source and patches (for DIY builders)
echo    OEL-DOCKER-!VERSION!.7z         - Docker source bundle (for Linux self-hosting)
echo.
echo  TSS files are not bundled. Users must obtain them separately.
echo ============================================================
pause
