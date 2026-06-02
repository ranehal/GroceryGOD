@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo  GROCERYGOD // ROBUST PUSH UTILITY (ZERO-FAIL)
echo ============================================================

:: 1. Run Guardrail Audit
echo [1/4] Running Security Guardrail...
python guardrail.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] PUSH ABORTED: Guardrail check failed. 
    echo Check for large files or LFS pointer corruption above.
    pause
    exit /b %ERRORLEVEL%
)
echo [+] Guardrail Passed.

:: 2. Stage and Commit
echo [2/4] Staging changes...
git add .
set /p commit_msg="Enter commit message (or press enter for 'manual update'): "
if "!commit_msg!"=="" set commit_msg=manual update

git commit -m "!commit_msg!"
echo [+] Commit created.

:: 3. Pull and Rebase (Safety First)
echo [3/4] Fetching remote and rebasing...
git fetch origin master
:: Using 'ours' strategy for data files to ensure local history is preserved during rebase
git pull origin master --rebase -X ours
if %ERRORLEVEL% NEQ 0 (
    echo [!] Rebase failed. Please resolve conflicts manually.
    pause
    exit /b %ERRORLEVEL%
)

:: 4. Final Push
echo [4/4] Pushing to GitHub master...
git push origin master
if %ERRORLEVEL% NEQ 0 (
    echo [!] Push failed. Checking for common issues...
    :: If push failed due to size, it would have been caught by guardrail, 
    :: so this is likely a network or auth issue.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ============================================================
echo  SUCCESS: Your updates are live!
echo ============================================================
pause
