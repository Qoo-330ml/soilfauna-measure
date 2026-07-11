"""Keyboard shortcuts reference dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
)

SHORTCUTS_HTML = """
<style>
  body { color: #1c1c1e; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif; }
  h3 { font-weight: 600; font-size: 15px; margin: 4px 0 12px 0; letter-spacing: -0.2px; }
  table { border-collapse: collapse; width: 100%; }
  td { padding: 6px 8px; vertical-align: top; }
  td:first-child { color: #007aff; font-family: ui-monospace, Menlo, monospace; white-space: nowrap; width: 42%; }
  tr.section td { color: #8e8e93; font-weight: 600; font-size: 11px; padding-top: 14px; letter-spacing: 0.3px; text-transform: uppercase; }
  .hint { color: #8e8e93; font-size: 12px; margin-top: 14px; }
</style>
<h3>快捷键</h3>
<table>
<tr class="section"><td colspan="2">文件</td></tr>
<tr><td>Ctrl+O</td><td>打开工作区</td></tr>
<tr><td>Ctrl+S</td><td>保存项目</td></tr>
<tr><td>Ctrl+Z / Ctrl+Shift+Z</td><td>撤销 / 重做</td></tr>
<tr><td>Ctrl+E</td><td>导出结果</td></tr>
<tr><td>Ctrl+B</td><td>批处理</td></tr>
<tr class="section"><td colspan="2">导航</td></tr>
<tr><td>PageUp / PageDown</td><td>上一张 / 下一张</td></tr>
<tr><td>滚轮</td><td>缩放（以光标为中心）</td></tr>
<tr><td>空白处拖动 / 空格 / 中键 / Ctrl+左键</td><td>拖拽平移图片</td></tr>
<tr><td>Ctrl+0 / Ctrl+1</td><td>适应窗口 / 1:1</td></tr>
<tr class="section"><td colspan="2">标注与测量</td></tr>
<tr><td>V</td><td>选择</td></tr>
<tr><td>P</td><td>多边形新建</td></tr>
<tr><td>B / E</td><td>画笔 / 橡皮</td></tr>
<tr><td>L</td><td>体长路径（追加节点）</td></tr>
<tr><td>H</td><td>小手调整体长</td></tr>
<tr><td>G</td><td>自动体长建议</td></tr>
<tr><td>C</td><td>比例尺手动校准</td></tr>
<tr><td>Shift+C</td><td>自动识别比例尺</td></tr>
<tr><td>A</td><td>自动分割</td></tr>
<tr><td>M</td><td>合并多选对象</td></tr>
<tr><td>S</td><td>切割线拆分</td></tr>
<tr><td>Delete / Backspace</td><td>删节点或对象</td></tr>
<tr><td>右键 / 双击节点</td><td>小手模式删除节点</td></tr>
<tr><td>R / X</td><td>体长反转 / 清空</td></tr>
<tr><td>[ ] / Ctrl·Shift·Alt+滚轮</td><td>画笔/橡皮粗细</td></tr>
<tr><td>工具栏 − / + / 数值框</td><td>画笔/橡皮粗细</td></tr>
<tr><td>0–7</td><td>分类快捷键</td></tr>
<tr><td>Enter</td><td>完成多边形 / 切割 / 种子</td></tr>
<tr><td>Esc</td><td>取消当前工具</td></tr>
</table>
<p class="hint">提示：在输入框中输入时，数字快捷键不会触发分类。</p>
"""


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("快捷键一览")
        self.resize(480, 560)
        browser = QTextBrowser()
        browser.setHtml(SHORTCUTS_HTML)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(browser)
        layout.addWidget(buttons)
