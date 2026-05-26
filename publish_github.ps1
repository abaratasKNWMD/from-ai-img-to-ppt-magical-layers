param(
  [string]$RepoName = "from-ai-img-to-ppt-magical-layers",
  [ValidateSet("public", "private", "internal")]
  [string]$Visibility = "public",
  [string]$Description = "Local AI image to layered PowerPoint converter with deterministic segmentation and optional OpenRouter judging."
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "GitHub CLI is not installed. Install it with: winget install --id GitHub.cli"
}

gh auth status | Out-Null

$branch = git branch --show-current
if ($branch -ne "main") {
  throw "Expected to publish from main, but current branch is '$branch'."
}

$remote = ""
try {
  $remote = git remote get-url origin
} catch {
  $remote = ""
}

if (-not $remote) {
  gh repo create $RepoName `
    --source "." `
    --remote "origin" `
    "--$Visibility" `
    --description $Description `
    --push
} else {
  git push -u origin main
}

gh repo view --web
