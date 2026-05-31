# 文档写作风格指南

QuantPilot 的文档不是给机器看的配置清单，而是给后来的人看的路标。代码会变，人的记忆也会掉线；一份好文档应该能让读者在半夜排障、第一次接手模块、或者隔几周回来继续开发时，都能快速找回上下文。

## 我们希望文档像什么

好的项目文档应该像一位熟悉系统的同事在旁边解释：

- 先告诉你这件事为什么重要。
- 再告诉你要看哪里、改哪里、怎么验证。
- 遇到坑时，不只说“失败”，还说“通常为什么失败”。
- 不假装系统永远完美，也不把临时绕法写成长期方案。

README 可以短一些，负责让人快速启动和找到入口。`docs/learning/` 可以更像教程，允许多解释一点基础知识和判断方法。专题文档则负责把长期规则写准。

## 少一点机器味

机器味重的文档通常有这些问题：

| 写法 | 问题 | 更好的写法 |
| --- | --- | --- |
| “本模块用于实现若干能力。” | 太空，没有告诉读者为什么要关心 | “这个模块负责把用户问题变成可验证工作空间。排查生成失败时，先从这里看。” |
| “执行以下命令。” | 只给动作，不给判断标准 | “先执行命令，再看是否出现 HTTP 200；如果失败，通常是后端没启动或端口被占用。” |
| “支持 X、Y、Z。” | 像功能广告 | “当你需要看 K 线、补数进度或数据质量时，策略平台会用到这些能力。” |
| “请参考相关文档。” | 读者不知道点哪一个 | “如果是数据字段缺失，先看 `docs/learning/03...`；如果是生成页面失败，先看 `docs/learning/02...`。” |
| 大段名词堆叠 | 读起来像接口列表 | 先用一句话讲人话，再放表格 |

写文档时可以多问自己一句：一个刚接手项目的人读到这里，会不会知道下一步该做什么？

## 推荐结构

一篇新的文档，优先用这个顺序：

1. 这篇文档解决什么问题。
2. 读完后应该能做什么。
3. 先解释基础概念，避免直接丢命令。
4. 给真实路径、真实命令和真实页面入口。
5. 写清楚成功如何判断。
6. 写常见误区和排障入口。
7. 最后给下一步阅读建议。

不是每篇都必须很长。小文档可以短，但也要有上下文。

## 什么时候用表格，什么时候用段落

表格适合做对照，例如组件职责、命令、文件路径、失败现象。段落适合讲为什么、讲取舍、讲经验。

如果整篇全是表格，会像机器生成的索引；如果整篇全是长段落，又很难查。比较舒服的节奏是：先用段落把问题讲明白，再用表格让读者快速定位。

## 写教程时要多讲一点基础知识

`docs/learning/` 的读者不一定已经懂 TimescaleDB、复权、run plan、evidence、skill、Loki 或评测。教程里可以用更朴素的解释：

- TimescaleDB 是带时序能力的 PostgreSQL，不是另一种连接协议。
- evidence 是数据证据，不是装饰文件。
- skill 是 Agent 的本地工作手册，不只是提示词。
- 降级模式是为了本地开发不断路，不是为了掩盖生产问题。

这些解释看起来啰嗦，但能减少很多后来人的误判。

## 使用 gpt-image2 增强教学文档

gpt-image2 适合生成概念图、流程图和学习地图，让读者先看见结构，再读细节。它不适合替代真实产品截图、接口响应、验证报告或精确字段表。

推荐用法：

- 用在 `docs/learning/` 中的概念解释，例如生成链路、skill 迭代闭环、数据流向。
- 图片里尽量少放小字；中文术语、路径、命令和判断标准放在正文和图注。
- 每张图都要有一句人话图注，告诉读者“这张图帮助理解什么”和“不能替代什么”。
- 生成图统一放在 `docs/learning/assets/`，文件名包含主题和 `gpt-image2`，例如 `workspace-generation-gpt-image2.png`。
- 如果图片是解释流程，正文中仍保留 Mermaid 或表格，方便搜索、复制和维护。

不推荐用法：

- 用 AI 图替代真实页面截图。
- 依赖图片中的细小文字作为唯一说明。
- 为了“好看”加入和项目无关的装饰场景。
- 把 gpt-image2 生成图当成验证证据。

可复用提示词骨架：

```text
Create a clean 16:9 educational illustration for QuantPilot documentation.
Show <流程或概念> using abstract UI cards, database, workflow arrows, validation icons, and light fintech engineering style.
Use a white or very light background, blue/teal accents, generous whitespace, and crisp edges.
Avoid tiny readable text, brand logos, watermarks, dark background, and clutter.
The image should teach structure, not replace the documentation text.
```

## 写排障文档时要像陪人一起查

排障文档不要只列错误名。更有用的写法是：

1. 先确认影响范围：只是一个页面坏了，还是整个服务不可用。
2. 给最小命令：例如 `npm run doctor`、`curl /health`。
3. 说明结果怎么读：哪些是 warning，哪些必须立刻修。
4. 给下一步：看日志、看验证报告、看数据表、看 skill。

排障文档最重要的不是“显得懂”，而是让人少绕路。

## 文档和代码必须一起走

下面这些改动，必须同步文档：

| 改动 | 至少同步 |
| --- | --- |
| 新页面、新平台入口 | README、`docs/README.md`、对应 learning 文档 |
| 新组件、新端口、新环境变量 | `docs/infrastructure.md`、`docs/troubleshooting.md`、`.env.example` |
| 新表、新字段、新 SQL | `sqls/README.md`、相关数据文档 |
| 新行情源或字段口径 | `docs/market-data-source-knowledge.md` |
| 生成工作空间契约变化 | `docs/generated-workspace-contract.md` |
| skill 边界或发布流程变化 | `docs/skills-governance.md`、`docs/learning/07-skills-authoring.md` |
| 新评测规则 | `docs/evals-guide.md`、`docs/learning/05-evaluation-and-operations.md` |

如果只是修一行代码但改变了用户理解方式，也值得补一句文档。

## 最后的小原则

- 少说“显而易见”。很多坑只对踩过的人显而易见。
- 少写“后续完善”。如果知道下一步是什么，就写清楚下一步。
- 不要把临时状态写成长期事实。
- 不要为了显得全面，把低价值细节塞满首页 README。
- 文档可以有一点温度，但不能牺牲准确性。

文档写得有人味，不是写得随意，而是让读者感觉自己不是一个人在摸黑。
