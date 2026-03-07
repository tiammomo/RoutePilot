# Naming Conventions

## 代码命名

1. Python 文件与模块: `snake_case`
2. Python 类名: `PascalCase`
3. Python 常量: `UPPER_SNAKE_CASE`
4. React 组件文件: `PascalCase.tsx`
5. TypeScript 非组件文件: 同目录保持统一（推荐 `camelCase.ts`）

## 文档命名

1. 文档文件名统一 `kebab-case.md`
2. 文档目录名统一小写英文
3. 所有项目文档统一归拢到 `docs/`

## 目录规则

1. 顶层目录只保留单一职责（`agent`/`web`/`frontend`/`docs`/`tests`）
2. 不保留历史兼容目录与冗余入口文档
3. 缓存、构建产物、运行时数据不纳入版本管理
