# Shared reader for SRC\PATCH\series -- the single source of truth for the OEL
# patch list and apply order. Dot-source this file, then call Get-PatchSeries.
#
# Returns ordered objects, one per patch:
#   Repo     target tree, lowercased (rpcs3 / rpcn)
#   RelPath  path relative to SRC\PATCH\ (as written in the series, forward slashes)
#   FullPath absolute path to the .patch file (backslashes)
#   Leaf     the patch filename
#
# Used by ci\build-all.ps1 and ci\build-rpcs3-only.ps1 so neither carries its
# own copy of the list. Add/remove/reorder a patch by editing SRC\PATCH\series.

function Get-PatchSeries {
    param(
        # Repo root; defaults to the parent of this script's ci\ directory.
        [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path,
        # Optional: only return patches for this target tree (e.g. 'rpcs3').
        [string]$RepoFilter
    )
    $series = Join-Path $RepoRoot "SRC\PATCH\series"
    if (-not (Test-Path $series)) { throw "Missing patch series file: $series" }

    $result = foreach ($raw in Get-Content -LiteralPath $series) {
        # Strip CR (the file can check out CRLF on a /mnt/c WSL mount), drop blank
        # lines and '#' comments, and keep the first whitespace-delimited token
        # (so a trailing "# comment" after the path is ignored).
        $line = $raw.TrimEnd("`r").Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { continue }
        $rel = ($line -split '\s+')[0]
        [pscustomobject]@{
            # Target tree = first path component, lowercased (RPCS3 -> rpcs3).
            Repo     = ($rel -split '[\\/]')[0].ToLowerInvariant()
            RelPath  = $rel
            FullPath = Join-Path $RepoRoot ("SRC\PATCH\" + ($rel -replace '/', '\'))
            Leaf     = ($rel -split '[\\/]')[-1]
        }
    }
    if ($RepoFilter) { $result = @($result | Where-Object { $_.Repo -eq $RepoFilter }) }
    if (-not $result) { throw "No patches parsed from $series" }
    return $result
}
