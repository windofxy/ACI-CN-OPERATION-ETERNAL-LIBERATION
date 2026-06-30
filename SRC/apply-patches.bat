@echo off
setlocal
set "SRC=%~dp0"
set "SERIES=%SRC%PATCH\series"

echo ============================================================
echo  ACI-RPCS3 -- Apply source patches
echo ============================================================
echo.

if not exist "%SERIES%" (
    echo ERROR: missing %SERIES%
    pause
    exit /b 1
)

:: The ordered patch list is SRC\PATCH\series -- the single source of truth.
:: Add, remove, reorder, or disable a patch by editing that file.
:: for /f skips blank lines; eol=# skips comment lines and trailing comments;
:: tokens=1 keeps just the patch path (relative to SRC\PATCH\). Each line is
:: handed to the :apply subroutine so plain %var% expansion stays reliable.

:: 1. Count the patch lines so the [N/total] counter is meaningful.
set /a total=0
for /f "usebackq eol=# tokens=1" %%P in ("%SERIES%") do set /a total+=1

:: 2. Apply each patch in order; abort on the first failure.
set /a idx=0
for /f "usebackq eol=# tokens=1" %%P in ("%SERIES%") do call :apply "%%P" || exit /b 1

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
exit /b 0

:: apply "<repo>/<patch>.patch" -- apply one series entry to its target tree.
:: Uses git -C instead of cd so the working directory never changes (a cd here
:: would stop cmd from re-finding this label on the next loop iteration).
:apply
set /a idx+=1
set "rel=%~1"
set "rel=%rel:/=\%"
:: Target tree = first path component (RPCS3 -> rpcs3, RPCN -> rpcn).
for /f "tokens=1 delims=/" %%R in ("%~1") do set "top=%%R"
set "repo="
if /i "%top%"=="RPCS3" set "repo=rpcs3"
if /i "%top%"=="RPCN"  set "repo=rpcn"
if not defined repo (
    echo.
    echo ERROR: unknown target tree "%top%" for %rel% in series.
    pause
    exit /b 1
)
echo [%idx%/%total%] Applying %rel%...
git -C "%SRC%GIT\%repo%" apply "%SRC%PATCH\%rel%"
if errorlevel 1 (
    echo.
    echo ERROR: failed to apply %rel%.
    echo Make sure SRC\GIT\%repo% is a clean clone with no local modifications.
    pause
    exit /b 1
)
echo Done.
echo.
exit /b 0
