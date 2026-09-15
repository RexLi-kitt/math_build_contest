$ErrorActionPreference = 'Stop'
$root = 'C:\Users\李\Desktop\math_build_contest\math_build_contest'
$archive = Join-Path $root '杂项文件夹\桌面归档_2026-09-15'
$original = @(Import-Csv -LiteralPath (Join-Path $archive '移动清单.csv'))
$hashes = @(Import-Csv -LiteralPath (Join-Path $archive '文件校验清单.csv'))
$destinations = @{
 '第三问模型改进机制报告'='src\q3\历史版本\桌面_2026-09-15\第三问模型改进机制报告'
 'B题机器狗离线模拟器'='src\q3\历史版本\桌面_2026-09-15\B题机器狗离线模拟器'
 'B题模型代码汇总'='src\q3\历史版本\桌面_2026-09-15\B题模型代码汇总'
 'Q3_bold_design'='src\q3\实验\Q3_bold_design'
 'Q3_oracle_test'='src\q3\实验\Q3_oracle_test'
 '第四问定向源实验'='src\q4\实验\第四问定向源实验'
 '第四问路线压缩'='src\q4\实验\第四问路线压缩'
 'Q4保底基线'='src\q4\实验\Q4保底基线'
 'Q4探索'='src\q4\实验\Q4探索'
 '正式测试结果'='outputs\正式测试结果\历史版本\桌面_2026-09-15'
 'CUMCM2026B'='比赛题目\B题\官方工具\CUMCM2026B'
 'B题.docx'='比赛题目\B题\历史版本\桌面_2026-09-15\B题.docx'
 '校对.docx'='paper\校对资料\校对.docx'
}
$moves = @()
foreach($item in $original) {
 $name = [IO.Path]::GetFileName($item.Source)
 if($name -eq '最终最终提交文件') {
  $moves += [pscustomobject]@{Source=(Join-Path $item.Destination '26B主论文.pdf');Destination=(Join-Path $root 'paper\最终提交\26B主论文.pdf')}
  $moves += [pscustomobject]@{Source=(Join-Path $item.Destination '支撑材料.zip');Destination=(Join-Path $root '支撑材料\提交原包\支撑材料.zip')}
 } else {
  if(!$destinations.ContainsKey($name)){throw "Unmapped: $name"}
  $moves += [pscustomobject]@{Source=$item.Destination;Destination=(Join-Path $root $destinations[$name])}
 }
}
foreach($move in $moves) {
 $from=[IO.Path]::GetFullPath($move.Source)
 $to=[IO.Path]::GetFullPath($move.Destination)
 if(!$from.StartsWith($archive+'\',[StringComparison]::OrdinalIgnoreCase) -or !$to.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Path boundary violation'}
 if(!(Test-Path -LiteralPath $from)){throw "Missing: $from"}
 if(Test-Path -LiteralPath $to){ if(!(Get-Item -LiteralPath $to).PSIsContainer -or @(Get-ChildItem -LiteralPath $to -Force).Count -gt 0){throw "Destination not empty: $to"} }
}
$newHashes = @()
foreach($file in $hashes){
 if((Get-FileHash -LiteralPath $file.Destination).Hash -ne $file.SHA256){throw "Source changed: $($file.Destination)"}
 $match = @($moves | Where-Object { $file.Destination -eq $_.Source -or $file.Destination.StartsWith($_.Source+'\',[StringComparison]::OrdinalIgnoreCase) })
 if($match.Count -ne 1){throw "Ambiguous mapping: $($file.Destination)"}
 $newHashes += [pscustomobject]@{DesktopSource=$file.Source;PreviousArchive=$file.Destination;Destination=$match[0].Destination+$file.Destination.Substring($match[0].Source.Length);Bytes=$file.Bytes;SHA256=$file.SHA256}
}
$logRoot=Join-Path $root 'docs\归档记录\2026-09-15'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$moves | Export-Csv -LiteralPath (Join-Path $logRoot '归位清单.csv') -NoTypeInformation -Encoding utf8
$newHashes | Export-Csv -LiteralPath (Join-Path $logRoot '文件校验清单.csv') -NoTypeInformation -Encoding utf8
foreach($file in $newHashes){
 New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($file.Destination)) -Force | Out-Null
 if(Test-Path -LiteralPath $file.Destination){throw "Refusing overwrite: $($file.Destination)"}
 Move-Item -LiteralPath $file.PreviousArchive -Destination $file.Destination
}
foreach($file in $newHashes){
 if((Get-FileHash -LiteralPath $file.Destination).Hash -ne $file.SHA256){throw "Verification failed: $($file.Destination)"}
}
$report = @"
# 数模桌面资料归位记录

2026-09-15：原归档中的14项数模资料已按仓库框架归位，共816个文件；最终提交目录拆为论文和支撑压缩包，因此归位清单共15条。所有文件移动前后 SHA256 一致，未覆盖或删除文件。

## 位置

- src/q3/实验：Q3_bold_design、Q3_oracle_test，保留脚本、说明及实验结果的内部结构。
- src/q3/历史版本/桌面_2026-09-15：第三问模型改进机制报告、B题机器狗离线模拟器、B题模型代码汇总。沿用第三问现有整包组织方式，包内第二问依赖一并保留。
- src/q4/实验：第四问定向源实验、第四问路线压缩、Q4保底基线、Q4探索；实验结果随代码保留，不混入已核对的论文输出。
- outputs/正式测试结果/历史版本/桌面_2026-09-15：桌面Q3、Q4正式测试原始资料。
- 比赛题目/B题/官方工具/CUMCM2026B：官方工具原始包、演示视频及下载说明。
- 比赛题目/B题/历史版本/桌面_2026-09-15/B题.docx：桌面题目原件，保留现有题目版本。
- paper/校对资料/校对.docx：校对文档。
- paper/最终提交/26B主论文.pdf：桌面最终提交论文原件。
- 支撑材料/提交原包/支撑材料.zip：桌面最终提交支撑包，未解压或改写。

## 版本与使用

第三问桌面资料与现有版本有差异：机制报告1个同名文件不同，离线模拟器3个不同且7个为桌面独有，代码汇总40个不同且12个为桌面独有。因此完整保留为历史版本，现有主线文件不变。
本次仅整理路径，没有重新运行模型；实验中引用的旧桌面绝对路径需在复现前按清单调整。不要将历史版本里的旧结论当作当前正式结论。

归位清单.csv 记录旧归档位置和新位置；文件校验清单.csv 记录原桌面位置、旧归档位置、新位置和 SHA256。
原杂项归档区仅保留历史操作记录和空目录，数模资料已全部归位。
"@
Set-Content -LiteralPath (Join-Path $logRoot 'README.md') -Value $report -Encoding utf8
Set-Content -LiteralPath (Join-Path $archive '归档说明.md') -Value "# 数模资料已归位`n`n全部816个数模文件已按仓库框架移出本目录。当前索引见 docs/归档记录/2026-09-15/README.md，当前路径和校验清单见该目录。此处移动清单等仅为历史记录，不代表当前文件位置。个人资料恢复记录保留。" -Encoding utf8
[pscustomobject]@{Moves=$moves.Count;VerifiedFiles=$newHashes.Count;Index=(Join-Path $logRoot 'README.md')} | ConvertTo-Json
