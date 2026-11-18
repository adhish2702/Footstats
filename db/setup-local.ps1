# Creates the local FootStats databases on a PostgreSQL server installed on this machine.
#
#   powershell -ExecutionPolicy Bypass -File db\setup-local.ps1     (from the repo root)
#
# What it does:
#   1. If there is no .env, writes one from .env.example with a random password
#      for a new "footstats" database user.
#   2. Connects as the "postgres" superuser (psql asks for that password; it is
#      the one you chose when installing PostgreSQL) and creates the "footstats"
#      user and the "footstats" and "footstats_test" databases. Safe to re-run.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"

# ---- 1. .env with a generated password ---------------------------------------------
if (-not (Test-Path $envFile)) {
    $chars = [char[]]"abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    $password = -join (1..24 | ForEach-Object { $chars | Get-Random })
    $example = Get-Content (Join-Path $root ".env.example") -Raw
    $example.Replace("change-me", $password) | Set-Content -Path $envFile -Encoding ascii -NoNewline
    Write-Host "Wrote .env with a new password for the footstats database user."
}

$line = Select-String -Path $envFile -Pattern '^DATABASE_URL=postgres(ql)?://([^:]+):([^@]+)@' | Select-Object -First 1
if (-not $line) { throw "DATABASE_URL in .env must look like postgresql://user:password@localhost:5432/footstats" }
$user = $line.Matches[0].Groups[2].Value
$password = $line.Matches[0].Groups[3].Value

# ---- 2. find psql ---------------------------------------------------------------------
$psql = Get-Command psql -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $psql) {
    $psql = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $psql) { throw "psql not found. Install PostgreSQL first: winget install PostgreSQL.PostgreSQL.17" }
Write-Host "Using $psql"

# ---- 3. create the user and databases ------------------------------------------------------
# The password is passed as a psql variable, so it is never written into the SQL file.
$sql = @"
DO `$`$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$user') THEN
    CREATE ROLE $user LOGIN;
  END IF;
END `$`$;
ALTER ROLE $user WITH LOGIN PASSWORD :'pw';
SELECT 'CREATE DATABASE footstats OWNER $user'
 WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'footstats') \gexec
SELECT 'CREATE DATABASE footstats_test OWNER $user'
 WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'footstats_test') \gexec
"@
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) "footstats-setup.sql"
Set-Content -Path $tmp -Value $sql -Encoding ascii
try {
    Write-Host "Connecting as the postgres superuser (enter the password you chose at install)..."
    & $psql -U postgres -h localhost -d postgres -v ON_ERROR_STOP=1 -v "pw=$password" -f $tmp
    if ($LASTEXITCODE -ne 0) { throw "psql failed (exit code $LASTEXITCODE)" }
} finally {
    Remove-Item $tmp -ErrorAction SilentlyContinue
}
Write-Host "Done: user '$user', databases 'footstats' and 'footstats_test'."
