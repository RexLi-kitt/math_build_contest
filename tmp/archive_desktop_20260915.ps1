$ErrorActionPreference = 'Stop'
$desktopRoot = [IO.Path]::GetFullPath([Environment]::GetFolderPath('Desktop'))
$workspaceRoot = 'C:\Users\李\Desktop\math_build_contest\math_build_contest'
$archiveRoot = Join-Path $workspaceRoot '杂项文件夹\桌面归档_2026-09-15'
$groups = [ordered]@{
 '比赛资料\第三问实验' = @('第三问模型改进机制报告','Q3_bold_design','Q3_oracle_test')
 '比赛资料\第四问实验' = @('第四问定向源实验','第四问路线压缩','Q4保底基线','Q4探索')
 '比赛资料\模型与离线模拟器' = @('B题机器狗离线模拟器','B题模型代码汇总')
 '比赛资料\正式测试' = @('正式测试结果')
 '比赛资料\最终提交' = @('最终最终提交文件')
 '比赛资料\官方工具原始包' = @('CUMCM2026B')
 '比赛资料\题目与校对文档' = @('B题.docx','校对.docx')
 '个人资料\电子书与PDF' = @('（备份）The Age of Openness - China_ (z-library.sk, 1lib.sk, z-lib.sk).pdf','836607-G.pdf','利用Python进行数据分析 原书第2版 (Wes McKinney) (z-library.sk, 1lib.sk, z-lib.sk).pdf','animal-farm.pdf','epdf.pub_the-fault-in-our-stars.pdf')
 '个人资料\图片与网页' = @('20260913T193836.png','20260914T111546.png','微信图片_20260818145209_2_43.jpg','comic-story.html','图片下载')
 '个人资料\代码片段' = @('untitled1.cpp')
}
New-Item -ItemType Directory -Path $archiveRoot -Force | Out-Null
$plan = @()
$inventory = @()
foreach ($category in $groups.Keys) {
 foreach ($name in $groups[$category]) {
  $source = [IO.Path]::GetFullPath((Join-Path $desktopRoot $name))
  $destination = [IO.Path]::GetFullPath((Join-Path (Join-Path $archiveRoot $category) $name))
  if ([IO.Path]::GetDirectoryName($source) -ne $desktopRoot) { throw "Source outside desktop: $source" }
  if (!$destination.StartsWith($archiveRoot + '\',[StringComparison]::OrdinalIgnoreCase)) { throw "Destination outside archive: $destination" }
  if (!(Test-Path -LiteralPath $source)) { throw "Missing source: $source" }
  if (Test-Path -LiteralPath $destination) { throw "Destination exists: $destination" }
  $item = Get-Item -LiteralPath $source -Force
  $entries = @($item)
  if ($item.PSIsContainer) { $entries += @(Get-ChildItem -LiteralPath $source -Recurse -Force) }
  if ($entries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw "Link found in $source; manual review needed" }
  foreach ($entry in $entries | Where-Object { !$_.PSIsContainer }) {
   $suffix = $entry.FullName.Substring($source.Length)
   $inventory += [pscustomobject]@{Source=$entry.FullName;Destination=$destination+$suffix;Bytes=$entry.Length;SHA256=(Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256).Hash}
  }
  $plan += [pscustomobject]@{Source=$source;Destination=$destination;Category=$category}
 }
}
$plan | Export-Csv -LiteralPath (Join-Path $archiveRoot '移动清单.csv') -NoTypeInformation -Encoding utf8
$inventory | Export-Csv -LiteralPath (Join-Path $archiveRoot '文件校验清单.csv') -NoTypeInformation -Encoding utf8
foreach ($entry in $plan) {
 New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($entry.Destination)) -Force | Out-Null
 Move-Item -LiteralPath $entry.Source -Destination $entry.Destination -ErrorAction Stop
 Add-Content -LiteralPath (Join-Path $archiveRoot '移动记录.txt') -Value ($entry.Source + ' -> ' + $entry.Destination) -Encoding utf8
}
foreach ($entry in $inventory) {
 if ((Get-FileHash -LiteralPath $entry.Destination -Algorithm SHA256).Hash -ne $entry.SHA256) { throw "Hash mismatch: $($entry.Destination)" }
}
$report = @"
# 桌面归档（2026-09-15）

已归档 $($plan.Count) 个桌面项目，共 $($inventory.Count) 个文件。全部文件移动前后 SHA256 校验一致。未删除任何文件。

## 分类

- 比赛资料：第三问实验、第四问实验、模型与离线模拟器、正式测试、最终提交、官方工具原始包、题目与校对文档。
- 个人资料：电子书与PDF、图片与网页、代码片段。未明确用途的PDF和图片完整保留。
- 移动清单.csv 记录原位置及新位置；文件校验清单.csv 记录每个文件的大小和校验值。恢复时按清单移回原位置，遇到同名文件不要覆盖。

## 桌面上可由你删除的文件

1. 你好.txt：0 字节空文件。
2. 20260914T111611.png：与已归档的 20260914T111546.png 的 SHA256 完全相同，重复内容。
3. untitled1.exe：与 untitled1.cpp 同名且生成时间相差约两秒，判断为编译产物；源码已归档。如果不需要直接运行，可删除。

## 保留在桌面的项目

- 大二学年代码、D2L、数学建模：独立学习项目，含 Git 仓库或虚拟环境，移动可能影响路径配置。
- jammers-simulator.exe、Jammers-simulator、JammersSimulatorData：模拟器及运行数据，数据最近仍有更新，保留原位置。
- 群星全dlc、PCL、Plain Craft Launcher 2.exe、Valorant：游戏文件、启动器和录像，不能认定为无用。
- 软件和游戏快捷方式、.vscode、desktop.ini、当前工作区父目录：保留原位置。

## 使用说明

实验目录保持原文件结构，部分代码和说明仍引用旧桌面绝对路径；重新运行时须按移动清单调整路径，本次未修改模型代码或验证模型运行。
本归档目录已加入 .gitignore，避免将个人文件及工具安装包意外提交到团队仓库。
"@
Set-Content -LiteralPath (Join-Path $archiveRoot '归档说明.md') -Value $report -Encoding utf8
[pscustomobject]@{MovedItems=$plan.Count;VerifiedFiles=$inventory.Count;TotalMB=[math]::Round(($inventory | Measure-Object Bytes -Sum).Sum/1MB,2);Archive=$archiveRoot} | ConvertTo-Json
