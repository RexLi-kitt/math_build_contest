"""兼容入口：Excel工作簿统一由 Artifact Tool 构建器生成。"""
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
NODE = shutil.which("node")
if NODE is None:
    raise RuntimeError("未找到 Node.js；请安装 Node.js 后运行 build_q2_workbook.mjs。")
subprocess.run([NODE, str(HERE / "build_q2_workbook.mjs")], check=True)
