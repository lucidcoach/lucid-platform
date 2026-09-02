[CmdletBinding()]
param([switch]$Check)

$source = $PSScriptRoot
$docs = Join-Path $source "docs"
$files = @("index.html", "app.js", "styles.css")
$directories = @("js", "css", "assets")

if (-not (Test-Path -LiteralPath $docs)) {
  New-Item -ItemType Directory -Path $docs | Out-Null
}

if ($Check) {
  $mismatches = @()
  foreach ($file in $files) {
    $sourcePath = Join-Path $source $file
    $docsPath = Join-Path $docs $file
    if (-not (Test-Path -LiteralPath $docsPath) -or (Get-FileHash -LiteralPath $sourcePath).Hash -ne (Get-FileHash -LiteralPath $docsPath).Hash) {
      $mismatches += $file
    }
  }
  foreach ($directory in $directories) {
    $sourceDirectory = Join-Path $source $directory
    foreach ($file in Get-ChildItem -LiteralPath $sourceDirectory -File -Recurse) {
      $relativeChild = $file.FullName.Substring($sourceDirectory.Length)
      $relativeChild = $relativeChild.TrimStart([char]92, [char]47)
      $relative = Join-Path $directory $relativeChild
      $docsPath = Join-Path $docs $relative
      if (-not (Test-Path -LiteralPath $docsPath) -or (Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $docsPath).Hash) {
        $mismatches += $relative
      }
    }
  }
  if ($mismatches.Count) {
    Write-Error ("docs is out of sync: " + ($mismatches -join ", "))
    exit 1
  }
  Write-Output "docs is in sync"
  exit 0
}

foreach ($file in $files) {
  Copy-Item -LiteralPath (Join-Path $source $file) -Destination (Join-Path $docs $file) -Force
}
foreach ($directory in $directories) {
  $sourceDirectory = Join-Path $source $directory
  $docsDirectory = Join-Path $docs $directory
  if (-not (Test-Path -LiteralPath $docsDirectory)) {
    New-Item -ItemType Directory -Path $docsDirectory | Out-Null
  }
  foreach ($file in Get-ChildItem -LiteralPath $sourceDirectory -File -Recurse) {
    $relativeChild = $file.FullName.Substring($sourceDirectory.Length)
    $relativeChild = $relativeChild.TrimStart([char]92, [char]47)
    $destination = Join-Path $docsDirectory $relativeChild
    $destinationParent = Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $destinationParent)) {
      New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    }
    Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
  }
}
Write-Output "Synced source homepage files to docs."
