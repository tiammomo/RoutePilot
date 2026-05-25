---
name: quant-image-extraction
description: Use this skill whenever a QuantPilot task includes uploaded images or .quantpilot/attachments.json, especially portfolio/account screenshots that need holdings, cost, cash, PnL, and position fields extracted before market data and visualization.
---

# QuantPilot 图片提取能力

本 skill 用于承接用户上传的图片附件，尤其是券商持仓、账户、成交或自选股截图。它负责把图片输入转换为可追溯的结构化证据，再交给行情、指标、数据质量和可视化能力继续处理。

## 何时必须使用

当出现以下任意情况时，必须先使用本能力：

- 用户上传了图片。
- 当前项目存在 `.quantpilot/attachments.json`。
- 用户问题包含“截图、图片、持仓、账户、仓位、调仓、盈亏、成本、可用、现金、总资产”等词。

## 标准流程

1. 读取 `.quantpilot/attachments.json`，确认附件路径、文件名、公开 URL 和提取契约。
2. 调用 `mcp__QuantPilotImage__quant_extract_uploaded_image`：
   - 默认参数：`{"attachmentContextPath": ".quantpilot/attachments.json", "prompt": "<用户问题>"}`
   - 该工具会校验图片文件是否存在，并返回格式、尺寸、哈希、字段契约和缺失字段。
3. 如果 `mcp__MiniMax__understand_image` 可用，再调用它识别图片视觉内容。
4. 将结果写入：

```text
evidence/image_extraction.json
```

5. 在最终数据中保留：

```text
data_file/final/dashboard-data.json -> imageExtraction
```

## 持仓截图字段契约

优先抽取：

- 账户：`account_total_asset`、`cash_available`、`market_value`、`daily_pnl`、`total_pnl`、`position_ratio`
- 持仓：`holdings[].name`、`holdings[].symbol_if_visible_or_resolved`、`holdings[].quantity`、`holdings[].cost_price`、`holdings[].current_price`、`holdings[].market_value`、`holdings[].pnl`、`holdings[].pnl_percent`
- 证据：图片路径、文件哈希、识别方式、需要人工确认的字段

无法确定的字段必须写 `null`，并放进 `needs_manual_confirmation_fields`，不要猜测或编造。

## 后续衔接

- 如果识别到股票名称或代码，下一步使用 `quant-symbol-resolver` 标准化标的。
- 如果识别到持仓数量、成本和现金，后续 `quant-market-data` 应获取实时行情和 K 线。
- `quant-data-quality` 必须把截图识别、行情补全和人工确认字段分开说明。
- `quant-visualization-html` 生成持仓/调仓看板时，必须展示图片字段来源和缺失项。

## 可见过程叙述要求

推荐输出：

```markdown
现在使用 `quant-image-extraction` 读取上传截图，先确认图片文件和可提取字段。

• Skill `quant-image-extraction` executing...

已确认图片文件存在，下一步识别持仓字段；无法确认的字段会写入 evidence/image_extraction.json。
```

## 禁止事项

- 不要忽略图片附件。
- 不要只说“我看不到图片”就停止。
- 不要把截图中没有出现的信息当作用户提供事实。
- 不要把视觉识别失败伪装成成功。
