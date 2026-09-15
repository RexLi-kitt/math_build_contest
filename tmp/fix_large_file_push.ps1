$ErrorActionPreference = 'Stop'
function Run-Git { & git @args; if($LASTEXITCODE -ne 0){throw "Git failed: $args"} }
$headBefore = (& git rev-parse HEAD).Trim()
if(!$headBefore.StartsWith('ba38f54')){throw 'HEAD changed; review required'}
$base = (& git rev-parse origin/main).Trim()
Run-Git merge-base --is-ancestor $base HEAD
$paths = @('比赛题目/B题/官方工具/CUMCM2026B/Jammers-simulator-full-win64.7z','比赛题目/B题/官方工具/CUMCM2026B/Jammers-simulator-win64.7z','比赛题目/B题/官方工具/CUMCM2026B/模拟器操作演示.mp4')
$before = @($paths | ForEach-Object { Get-FileHash -LiteralPath $_ })
Run-Git branch codex/backup-before-large-file-ignore-20260915 $headBefore
Run-Git rm --cached -- $paths
Run-Git add -- .gitignore
$expectedTree = (& git write-tree).Trim()
if($LASTEXITCODE -ne 0){throw 'Cannot write tree'}
Run-Git reset --soft $base
Run-Git commit -m '归档数模资料，忽略本地官方安装包和演示视频'
$actualTree = (& git rev-parse 'HEAD^{tree}').Trim()
if($actualTree -ne $expectedTree){throw 'Committed content mismatch'}
foreach($file in $before){if((Get-FileHash -LiteralPath $file.Path).Hash -ne $file.Hash){throw 'Local file changed'}}
Run-Git status -sb
Run-Git log --oneline origin/main..HEAD
Write-Output 'Local files verified unchanged; backup branch retained. No push performed.'
