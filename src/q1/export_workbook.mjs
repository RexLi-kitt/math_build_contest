// 读取实验快照生成 Excel；不在 Excel 中重新实现几何算法。
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
import {pathToFileURL, fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
// 直接解析运行时依赖，不再依赖项目 tmp 下的 node_modules 目录链接。
const modules = process.env.Q1_NODE_MODULES || path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const require = createRequire(path.join(path.dirname(modules), '__q1_runtime_resolver__.cjs'));
const {Workbook, SpreadsheetFile} = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const input = path.resolve(process.argv[2] || path.join(root, 'src/q1/results/experiment_data.json'));
const out = path.resolve(process.argv[3] || path.join(root, 'outputs/q1/tables/Q1_定位实验.xlsx'));
const previewDir = await fs.mkdtemp(path.join(os.tmpdir(), 'q1-export-'));
try {
const data = JSON.parse(await fs.readFile(input, 'utf8'));
const wb = Workbook.create();
const status = {empty:'空集',unbounded:'无界',point:'单点',segment:'线段',polygon:'凸多边形',error:'计算错误'};
const yes = value => value == null ? '不适用' : value ? '是' : '否';
const checked = value => value == null ? '不适用' : value ? '通过' : '失败';
const numeric = value => value === '∞' ? '∞' : value;
await fs.mkdir(path.dirname(out), {recursive:true});

function makeSheet(name, title, context, headers, rows, widths, tableName) {
  const sheet = wb.worksheets.add(name);
  sheet.showGridLines = false;
  const last = 6 + rows.length;
  const grid = sheet.getRangeByIndexes(0,0,last,headers.length);
  grid.format.font = {name:'Microsoft YaHei',size:10,color:'#243447'};
  grid.format.rowHeight = 22;
  grid.format.verticalAlignment = 'center';
  sheet.getRange('A2').values = [[title]];
  sheet.getRange('A2').format.font = {name:'Microsoft YaHei',size:15,bold:true,color:'#17365D'};
  sheet.getRange('A2').format.rowHeight = 28;
  sheet.getRange('A3').values = [[context]];
  sheet.getRange('A3').format.font = {name:'Microsoft YaHei',size:10,color:'#536579'};
  sheet.getRangeByIndexes(5,0,1,headers.length).values = [headers];
  if (rows.length) sheet.getRangeByIndexes(6,0,rows.length,headers.length).values = rows;
  widths.forEach((width,i)=>sheet.getRangeByIndexes(0,i,last,1).format.columnWidthPx=width);
  const table = sheet.tables.add(sheet.getRangeByIndexes(5,0,rows.length+1,headers.length),true,tableName);
  table.showFilterButton = true;
  sheet.getRangeByIndexes(5,0,1,headers.length).format = {
    fill:'#17365D',font:{name:'Microsoft YaHei',size:10,bold:true,color:'#FFFFFF'},
    horizontalAlignment:'center',verticalAlignment:'center',rowHeight:32,
  };
  sheet.freezePanes.freezeRows(6);
  sheet.freezePanes.freezeColumns(2);
  return sheet;
}

const headers=['组号','类型','S_x (m)','S_y (m)','监测点数','区域状态','直径 (m)','同直径圆覆盖','检查结果'];
for(let i=1;i<=6;i++) headers.push(`M${i}_x (m)`,`M${i}_y (m)`);
headers.push('真值在区域内','顶点满足约束','两算法直径一致','圆外超出量 (m)');
const summaryRows=data.cases.map(c=>{
  const row=[c.case_id,c.kind,...c.source,c.stations.length,status[c.status],numeric(c.diameter_m),yes(c.circle_covers),checked(c.passed)];
  for(let i=0;i<6;i++) row.push(...(c.stations[i]||[null,null]));
  row.push(checked(c.checks.truth_inside_polygon ?? c.checks.truth_satisfies_halfplanes),
    checked(c.checks.vertices_satisfy_halfplanes),checked(c.checks.diameters_match_exactly),c.circle_excess_m??null);
  return row;
});
const main=makeSheet('定位实验', 'Q1 随机交会定位实验',
  `${data.summary.random_count}组随机算例 + 最后一组等边三角形反例；S为真实干扰源，M为监测点。`,
  headers,summaryRows,[95,165,125,125,85,100,125,120,95,...Array(12).fill(125),125,125,145,145], 'LocalizationCases');
main.tabColor='#17365D';
main.getRange(`C7:D${6+summaryRows.length}`).setNumberFormat('0.000000');
main.getRange(`G7:G${6+summaryRows.length}`).setNumberFormat('0.000000');
main.getRange(`J7:U${6+summaryRows.length}`).setNumberFormat('0.000000');
main.getRange(`Y7:Y${6+summaryRows.length}`).setNumberFormat('0.000000000');
main.getRange(`I7:I${6+summaryRows.length}`).conditionalFormats.add('containsText',{text:'失败',format:{fill:'#FDE9E7',font:{color:'#A61B1B',bold:true}}});
main.getRange(`A${6+summaryRows.length}:Y${6+summaryRows.length}`).format.fill='#FFF0DF';
main.getRange('A4').values=[['空白监测坐标表示本组未设置该监测点；“否”是圆覆盖结论，不等于算法检查失败。']];

const obs=data.cases.flatMap(c=>c.observations);
const observationRows=obs.map(o=>[o.case_id,o.monitor,o.x,o.y,o.source_x,o.source_y,o.true_bearing_deg,o.error_deg,o.measured_bearing_deg,o.distance_to_source_m]);
const observation=makeSheet('观测明细','逐次监测的输入数据',
  `种子 ${data.metadata.seed}；模拟误差均匀抽取于[-1°,1°]，仅为实验设定。每行对应一次有效测向。`,
  ['组号','监测点','M_x (m)','M_y (m)','S_x (m)','S_y (m)','真实方位 (°)','加入误差 (°)','示向度 (°)','源点距离 (m)'],
  observationRows,[95,85,125,125,125,125,145,145,145,145], 'BearingObservations');
observation.getRange(`C7:F${6+obs.length}`).setNumberFormat('0.000000');
observation.getRange(`G7:I${6+obs.length}`).setNumberFormat('0.000000000');
observation.getRange(`J7:J${6+obs.length}`).setNumberFormat('0.000000');
observation.getRange('A4').values=[['坐标保留原始数值，显示6位小数；表内结果为运行快照，更改输入需重跑Python。']];

const edgeRows=data.boundary_cases.map(c=>[c.case_id,c.case,c.layer,status[c.expected_status],status[c.actual_status],numeric(c.diameter_m),checked(c.passed),c.input,c.handling]);
const edge=makeSheet('边界测试与方法','边界情况及处理方式',
  `${data.summary.edge_count}项确定性测试；空集和无界也是正确状态，不纳入有限直径均值。`,
  ['编号','测试情况','测试层','预期状态','实际状态','直径 (m)','检查结果','构造输入','处理方式'],
  edgeRows,[95,200,145,100,100,160,95,550,650], 'BoundaryCases');
edge.getRange(`F7:F${6+edgeRows.length}`).setNumberFormat('0.000000');
edge.getRange(`G7:G${6+edgeRows.length}`).conditionalFormats.add('containsText',{text:'失败',format:{fill:'#FDE9E7',font:{color:'#A61B1B',bold:true}}});
// 边界测试的定义较长，独立给这些行足够高度，避免输入与处理说明截断。
edge.getRange(`H7:I${6+edgeRows.length}`).format.wrapText=true;
edge.getRange(`A7:I${6+edgeRows.length}`).format.rowHeight=52;
const start=6+edgeRows.length+3;
const notes=[
  ['实验方法','取值或说明'],
  ['随机种子',data.metadata.seed],
  ['S点抽样',data.metadata.source_sampling],
  ['监测点抽样',data.metadata.monitor_sampling],
  ['每组监测点数',data.metadata.monitor_count],
  ['误差抽样',data.metadata.error_sampling],
  ['样本保留规则',data.metadata.retention],
  ['随机样本检查','真值满足角度约束且位于输出区域；顶点满足全部约束；旋转卡壳与枚举的距离平方精确一致。'],
  ['无界样本检查','若出现无界，核对非零延伸方向满足全部齐次半平面约束；不伪造有限直径。'],
  ['等边三角形理论边长 (m)',20],
  ['理论直径 (m)',20],
  ['同直径圆半径 (m)',null],
  ['最小外接圆半径 (m)',null],
  ['反例含义','最小外接圆半径大于D/2，所以不存在同直径覆盖圆；主表最后一组是三次测向实际生成的近似等边三角形。'],
  ['三角形数值比较容差','1e-8米；浮点三角函数产生的近似不作为符号精确等边三角形。'],
  ['推断范围','随机样本通过说明这些样本未发现错误，不替代几何证明，也不代表所有输入都能成功定位。'],
  ['精度限制','几何谓词对输入系数使用有理数精确计算；测向角到方向向量仍有三角函数舍入。'],
  ['复算方式',data.metadata.recalculation],
];
// 将说明放在A和B:I区域；不合并单元格，长说明使用独立宽列H。
edge.getRangeByIndexes(start-1,0,notes.length,1).values=notes.map(r=>[r[0]]);
edge.getRangeByIndexes(start-1,7,notes.length,1).values=notes.map(r=>[r[1]]);
edge.getRangeByIndexes(start-1,0,notes.length,9).format.font={name:'Microsoft YaHei',size:10,color:'#243447'};
edge.getRangeByIndexes(start-1,7,notes.length,1).format.wrapText=true;
edge.getRangeByIndexes(start-1,0,notes.length,9).format.rowHeight=42;
edge.getRange(`H${start+11}`).formulas=[[`=H${start+10}/2`]];
edge.getRange(`H${start+12}`).formulas=[[`=H${start+9}/SQRT(3)`]];
edge.getRange(`H${start+9}:H${start+12}`).setNumberFormat('0.000000');
// 标签跨越空白单元格显示，不会影响平面的原始数据表。
edge.getRange(`A${start}:I${start}`).format.fill='#E8EEF5';

wb.recalculate();
console.log((await wb.inspect({kind:'table',range:`定位实验!A${6+summaryRows.length}:I${6+summaryRows.length}`,include:'values,formulas',tableMaxRows:1,tableMaxCols:9,maxChars:1800})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',options:{useRegex:true,maxResults:10},maxChars:1000})).ndjson);
for (const [name,range,file] of [
  ['定位实验','A1:I13','summary.png'],
  ['定位实验',`A${3+summaryRows.length}:I${6+summaryRows.length}`,'triangle.png'],
  ['观测明细','A1:J12','observations.png'],
  ['边界测试与方法','A1:G15','boundary.png'],
]) {
  const preview=await wb.render({sheetName:name,range,scale:1.3,format:'png'});
  await fs.writeFile(path.join(previewDir,file),new Uint8Array(await preview.arrayBuffer()));
}
const xlsx=await SpreadsheetFile.exportXlsx(wb);
// 导出器会附带检查日志；先写系统临时目录，只保留正式工作簿。
const staged = path.join(previewDir, 'Q1_定位实验.xlsx');
await xlsx.save(staged);
await fs.copyFile(staged, out);
console.log(JSON.stringify({output:out,cases:summaryRows.length,observations:obs.length,boundary:edgeRows.length}));
} finally {
  // 只清理本次 mkdtemp 创建的目录；需要检查预览时可显式保留。
  if (process.env.Q1_KEEP_PREVIEWS === '1') console.log(`预览保留在：${previewDir}`);
  else await fs.rm(previewDir, {recursive:true, force:true});
}
