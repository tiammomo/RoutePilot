---
name: quant-symbol-resolver
description: Use this skill when the user mentions a stock name, abbreviation, ticker, or ambiguous security identifier that must be resolved before data retrieval.
---

# QuantPilot 证券标识解析能力

把用户输入的股票名称、简称、拼音或代码解析成标准证券代码和东方财富 `secid`。

## API

```bash
curl 'http://127.0.0.1:8000/api/v1/symbols/resolve?query=茅台&count=5'
curl 'http://127.0.0.1:8000/api/v1/symbols/resolve?query=600519&count=5'
```

## 工作流程

1. 用户没有给出明确 6 位代码时，先调用本能力。
2. 优先选择 A 股结果，并记录 `symbol`、`name`、`market`、`secid`。
3. 若存在多个候选，展示候选并说明你选择的依据。
4. 后续行情、K 线、财务、公告查询使用解析后的 `symbol` 或 `secid`。

## 禁止事项

- 不要把中文股票名直接传给行情接口。
- 不要在存在多个候选时假定唯一结果。
