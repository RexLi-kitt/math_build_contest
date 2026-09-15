$ErrorActionPreference = 'Stop'
$workspaceRoot = 'C:\Users\李\Desktop\math_build_contest\math_build_contest'
$archiveRoot = Join-Path $workspaceRoot '杂项文件夹\桌面归档_2026-09-15'
$desktopRoot = [IO.Path]::GetFullPath([Environment]::GetFolderPath('Desktop'))
$planPath = Join-Path $archiveRoot '移动清单.csv'
$hashPath = Join-Path $archiveRoot '文件校验清单.csv'
$plan = @(Import-Csv -LiteralPath $planPath)
$inventory = @(Import-Csv -LiteralPath $hashPath)
$restore = @($plan | Where-Object Category -like '个人资料*')
$missing = @($restore | Where-Object { !(Test-Path -LiteralPath $_.Destination) -and !(Test-Path -LiteralPath $_.Source) })
$restore = @($restore | Where-Object { Test-Path -LiteralPath $_.Destination })
$keep = @($plan | Where-Object Category -notlike '个人资料*')
$personalRoot = Join-Path $archiveRoot '个人资料'
$restoreFiles = @($inventory | Where-Object { $_.Destination.StartsWith($personalRoot + '\', [StringComparison]::OrdinalIgnoreCase) })
$restoreFiles = @($restoreFiles | Where-Object { Test-Path -LiteralPath $_.Destination })
$keepFiles = @($inventory | Where-Object { !$_.Destination.StartsWith($personalRoot + '\', [StringComparison]::OrdinalIgnoreCase) })
foreach ($entry in $restore) {
 $from = [IO.Path]::GetFullPath($entry.Destination)
 $to = [IO.Path]::GetFullPath($entry.Source)
 if (!$from.StartsWith($personalRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Archive boundary violation: $from" }
 if ([IO.Path]::GetDirectoryName($to) -ne $desktopRoot) { throw "Desktop boundary violation: $to" }
 if (!(Test-Path -LiteralPath $from)) { throw "Missing: $from" }
 if (Test-Path -LiteralPath $to) { throw "Desktop destination exists, refusing overwrite: $to" }
}
foreach ($entry in $restoreFiles) {
 if ((Get-FileHash -LiteralPath $entry.Destination -Algorithm SHA256).Hash -ne $entry.SHA256) { throw "File changed: $($entry.Destination)" }
}
foreach ($entry in $restore) {
 Move-Item -LiteralPath $entry.Destination -Destination $entry.Source
 Add-Content -LiteralPath (Join-Path $archiveRoot '移动记录.txt') -Value ('恢复个人资料：' + $entry.Destination + ' -> ' + $entry.Source) -Encoding utf8
}
foreach ($entry in $restoreFiles) {
 if ((Get-FileHash -LiteralPath $entry.Source -Algorithm SHA256).Hash -ne $entry.SHA256) { throw "Restored file mismatch: $($entry.Source)" }
}
$restore | Export-Csv -LiteralPath (Join-Path $archiveRoot '已恢复桌面清单.csv') -NoTypeInformation -Encoding utf8
$missing | Export-Csv -LiteralPath (Join-Path $archiveRoot '原位置与归档位置均缺失.csv') -NoTypeInformation -Encoding utf8
$keep | Export-Csv -LiteralPath $planPath -NoTypeInformation -Encoding utf8
$keepFiles | Export-Csv -LiteralPath $hashPath -NoTypeInformation -Encoding utf8
$report = @"
# 数学建模桌面归档（2026-09-15）

归档范围仅限数学建模资料。当前保留 $($keep.Count) 个桌面项目，共 $($keepFiles.Count) 个文件。
误归档的 $($restore.Count) 个个人项目（$($restoreFiles.Count) 个文件）已恢复桌面原位置，逐文件 SHA256 校验一致，未删除或覆盖文件。

## 当前分类

比赛资料：第三问实验、第四问实验、模型与离线模拟器、正式测试、最终提交、官方工具原始包、题目与校对文档。
电子书、图片下载文件夹、现存散落图片、网页和个人代码已恢复桌面。
恢复前发现微信图片_20260818145209_2_43.jpg 在归档位置和桌面原位置均不存在，无法恢复，已单独记录；本次操作未删除该文件。

## 清单

- 移动清单.csv：当前仍归档的数模项目及其原位置。
- 文件校验清单.csv：当前数模归档文件的大小和 SHA256。
- 已恢复桌面清单.csv：已撤销归档的个人项目。
- 移动记录.txt：完整移动及恢复历史。

## 保留在桌面的数模目录

数学建模目录含独立仓库和虚拟环境；jammers-simulator.exe、Jammers-simulator、JammersSimulatorData 为模拟器及运行数据，暂留原位置以避免影响运行。

## 使用说明

实验目录保持原结构，部分代码和说明仍引用旧桌面绝对路径；重新运行时须按移动清单调整，本次未修改模型代码或验证模型运行。
本归档目录已加入 .gitignore，避免工具安装包等意外提交到团队仓库。
个人文件不属于本次整理范围，不再列入本次数模清理建议。
"@
Set-Content -LiteralPath (Join-Path $archiveRoot '归档说明.md') -Value $report -Encoding utf8
[pscustomobject]@{RestoredItems=$restore.Count;VerifiedRestoredFiles=$restoreFiles.Count;RemainingArchiveItems=$keep.Count;RemainingArchiveFiles=$keepFiles.Count} | ConvertTo-Json
