@echo off
setlocal
set "SRC=%~dp0"

echo ============================================================
echo  ACI-RPCS3 -- Apply source patches
echo ============================================================
echo.

echo [1/9] Applying RPCS3 TSS patch...
cd /d "%SRC%GIT\rpcs3"
git apply "..\..\PATCH\RPCS3\tss-support.patch"
if errorlevel 1 (
    echo.
    echo ERROR: RPCS3 TSS patch failed.
    echo Make sure SRC\GIT\rpcs3 is a clean clone with no local modifications.
    pause & exit /b 1
)
echo Done.
echo.

echo [2/9] Applying RPCS3 P2PS disconnect fix patch...
cd /d "%SRC%GIT\rpcs3"
git apply "..\..\PATCH\RPCS3\p2ps-disconnect-fix.patch"
if errorlevel 1 (
    echo.
    echo ERROR: RPCS3 P2PS patch failed.
    echo Make sure SRC\GIT\rpcs3 is a clean clone with no local modifications.
    pause & exit /b 1
)
echo Done.
echo.

echo [3/9] Applying RPCS3 tree transparency patch...
cd /d "%SRC%GIT\rpcs3"
git apply "..\..\PATCH\RPCS3\tree-transparency.patch"
if errorlevel 1 (
    echo.
    echo ERROR: RPCS3 tree transparency patch failed.
    echo Make sure SRC\GIT\rpcs3 is a clean clone with no local modifications.
    pause & exit /b 1
)
echo Done.
echo.

echo [4/9] Applying RPCS3 NP LocalNetInfo byte order fix patch...
cd /d "%SRC%GIT\rpcs3"
git apply "..\..\PATCH\RPCS3\np-localnetinfo-byteorder-fix.patch"
if errorlevel 1 (
    echo.
    echo ERROR: RPCS3 NP LocalNetInfo byte order fix patch failed.
    echo Make sure SRC\GIT\rpcs3 is a clean clone with no local modifications.
    pause & exit /b 1
)
echo Done.
echo.

echo [5/9] Applying RPCS3 NP signaling GetConnectionInfo disconnect fix patch...
cd /d "%SRC%GIT\rpcs3"
git apply "..\..\PATCH\RPCS3\np-signaling-conninfo-disconnect.patch"
if errorlevel 1 (
    echo.
    echo ERROR: RPCS3 NP signaling GetConnectionInfo disconnect fix patch failed.
    echo Make sure SRC\GIT\rpcs3 is a clean clone with no local modifications.
    pause & exit /b 1
)
echo Done.
echo.

echo [6/9] Applying RPCS3 NP disconnect handling patch...
cd /d "%SRC%GIT\rpcs3"
git apply "..\..\PATCH\RPCS3\np-disconnect-handling.patch"
if errorlevel 1 (
    echo.
    echo ERROR: RPCS3 NP disconnect handling patch failed.
    echo Make sure SRC\GIT\rpcs3 is a clean clone with no local modifications.
    pause & exit /b 1
)
echo Done.
echo.

echo [7/9] Applying RPCS3 P2PS disconnect diagnostics patch...
cd /d "%SRC%GIT\rpcs3"
git apply "..\..\PATCH\RPCS3\p2ps-disconnect-diagnostics.patch"
if errorlevel 1 (
    echo.
    echo ERROR: RPCS3 P2PS disconnect diagnostics patch failed.
    echo Make sure SRC\GIT\rpcs3 is a clean clone with no local modifications.
    pause & exit /b 1
)
echo Done.
echo.

echo [8/9] Applying RPCS3 frame limit lock patch...
cd /d "%SRC%GIT\rpcs3"
git apply "..\..\PATCH\RPCS3\framelimit-lock.patch"
if errorlevel 1 (
    echo.
    echo ERROR: RPCS3 frame limit lock patch failed.
    echo Make sure SRC\GIT\rpcs3 is a clean clone with no local modifications.
    pause & exit /b 1
)
echo Done.
echo.

echo [9/9] Applying RPCN TSS server patch...
cd /d "%SRC%GIT\rpcn"
git apply "..\..\PATCH\RPCN\tss-server.patch"
if errorlevel 1 (
    echo.
    echo ERROR: RPCN patch failed.
    echo Make sure SRC\GIT\rpcn is a clean clone with no local modifications.
    pause & exit /b 1
)
echo Done.
echo.

echo ============================================================
echo  All patches applied successfully.
echo.
echo  Next steps:
echo    RPCS3: Follow SRC\GIT\rpcs3\BUILDING.md (Visual Studio 2022)
echo           Copy output rpcs3.exe + DLLs to BIN\RPCS3\
echo.
echo    RPCN:  cd SRC\GIT\rpcn
echo           cargo build --release
echo           Copy target\release\rpcn.exe to BIN\rpcn\
echo ============================================================
pause
