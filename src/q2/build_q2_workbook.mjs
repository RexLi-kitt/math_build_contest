/** Rebuild the Q2 workbook from the latest CSV tables with Artifact Tool. */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const sourceDir = path.join(root, "outputs", "q2", "tables");
const outputPath = path.join(sourceDir, "Q2_第二检测点实验.xlsx");
const previewDir = path.join(here, "workbook_previews");
const sheets = [
  ["候选点评分", "Q2候选点评分.csv", "独立A1/A2物理域上的四指标归一化联合评分"],
  ["候选区域", "Q2候选区域.csv", "评分达到峰值90%以上的第二检测点区域及执行点"],
  ["策略对比", "Q2策略对比.csv", "联合、仅几何、最近点与随机点的样本回放比较"],
  ["权重敏感性", "Q2权重敏感性.csv", "各权重±10%扰动后的最优点稳定性"],
  ["闭环检验", "Q2闭环检验.csv", "no_signal 的1000m保证接收圆盘排除检验"],
  ["接收逻辑检验", "Q2接收逻辑检验.csv", "接收半径1000--1500m的蒙特卡洛逻辑核验"],
  ["边界测试", "Q2边界测试.csv", "极端角度、退化几何与物理候选域的边界验证"],
];

function parseCsv(text) {
  // The generated CSVs contain no embedded newlines; this parser still supports quoted commas.
  return text.trim().split(/\r?\n/).map(line => {
    const cells = []; let cur = ""; let quoted = false;
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i];
      if (ch === '"') { if (quoted && line[i + 1] === '"') { cur += '"'; i += 1; } else quoted = !quoted; }
      else if (ch === "," && !quoted) { cells.push(cur); cur = ""; }
      else cur += ch;
    }
    cells.push(cur);
    return cells.map(v => (/^-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(v) ? Number(v) : v));
  });
}

const workbook = Workbook.create();
for (let i = 0; i < sheets.length; i += 1) {
  const [name, file, note] = sheets[i];
  const csvText = await fs.readFile(path.join(sourceDir, file), "utf8");
  const rows = parseCsv(csvText.replace(/^\uFEFF/, ""));
  if (rows.length < 2) throw new Error(`${file} has no data rows`);
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  sheet.tabColor = i === 0 ? "#17365D" : (i === 1 ? "#1F5A94" : "#7F9DB9");
  const colCount = rows[0].length;
  const lastColumn = String.fromCharCode(64 + colCount);

  sheet.getRange("A1").values = [["问题2 第二检测点实验"]];
  sheet.getRange("A1").format = {
    font: { name: "Arial", size: 15, bold: true, color: "#17365D" },
    verticalAlignment: "center",
  };
  sheet.getRange(`A3:${lastColumn}3`).format.borders = {
    preset: "insideHorizontal", style: "thin", color: "#1F5A94",
  };
  sheet.getRange("A2").values = [[note]];
  sheet.getRange("A2").format = { font: { name: "Arial", size: 10, color: "#536579", italic: true } };
  sheet.getRange(`A4:${lastColumn}${rows.length + 3}`).values = rows;
  const header = sheet.getRange(`A4:${lastColumn}4`);
  header.format = {
    fill: "#17365D",
    font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#FFFFFF" },
  };
  const body = sheet.getRange(`A5:${lastColumn}${rows.length + 3}`);
  body.format = {
    font: { name: "Arial", size: 10, color: "#1F2937" },
    verticalAlignment: "center",
    numberFormat: "0.000",
  };
  body.format.borders = { preset: "insideHorizontal", style: "thin", color: "#D9E2F3" };
  // 仅强调有解释意义的关键结果，不以整表颜色干扰论文阅读。
  if (name === "候选区域") {
    rows.slice(1).forEach((row, rowIndex) => {
      if (row.includes("是")) {
        sheet.getRangeByIndexes(rowIndex + 4, 0, 1, colCount).format = {
          fill: "#FCE4D6",
          font: { name: "Arial", size: 10, bold: true, color: "#9C4A0B" },
        };
      }
    });
  }
  if (name === "候选点评分") {
    const scoreColumn = rows[0].indexOf("score");
    const maxScore = Math.max(...rows.slice(1).map(row => Number(row[scoreColumn])));
    rows.slice(1).forEach((row, rowIndex) => {
      if (Number(row[scoreColumn]) >= maxScore - 1e-12) {
        sheet.getRangeByIndexes(rowIndex + 4, 0, 1, colCount).format = {
          fill: "#EAF3FB",
          font: { name: "Arial", size: 10, bold: true, color: "#17365D" },
        };
      }
    });
  }
  for (let c = 0; c < colCount; c += 1) {
    const column = sheet.getRangeByIndexes(0, c, rows.length + 3, 1);
    // Keep long scientific field names visible; body values are displayed to 3 decimals.
    column.format.columnWidth = Math.min(Math.max(String(rows[0][c]).length * 1.2 + 4, 13), 38);
  }
  sheet.getRange(`A4:${lastColumn}4`).format.rowHeight = 34;
  sheet.freezePanes.freezeRows(4);
  const table = sheet.tables.add(`A4:${lastColumn}${rows.length + 3}`, true, `Q2Table${i + 1}`);
  table.style = "TableStyleMedium2";
  table.showBandedRows = true;
}

workbook.recalculate();
const summary = await workbook.inspect({ kind: "workbook,sheet,table", maxChars: 5000, tableMaxRows: 5, tableMaxCols: 8 });
console.log(summary.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" });
console.log(errors.ndjson);
await fs.mkdir(previewDir, { recursive: true });
for (const [name] of sheets) {
  const preview = await workbook.render({ sheetName: name, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, `${name}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`Saved ${outputPath}`);
