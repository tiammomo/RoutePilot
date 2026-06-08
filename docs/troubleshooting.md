# 故障排查

## 数据库不可用

1. 检查 `.env` 中的 `DATABASE_URL`。
2. 新环境运行 `npm run db:up`。
3. 初始化旅游 schema：`npm run db:init`。
4. 导入本地旅游数据：`npm run travel:db:import`。
5. 检查数据状态：`npm run travel:db:doctor`。

如果你已经使用旧数据库名保存了通勤采集结果，可以继续沿用旧 `DATABASE_URL`，无需重建数据库。

## 通勤数据不完整

运行：

```bash
npm run check:travel-commute
```

通勤边数据表是 `travel_commute_edges`。默认采集目标覆盖景点-景点、景点-餐厅、餐厅-餐厅三类关系。

## 旅游规划 API 异常

运行：

```bash
npm run check:travel-query-plan
npm run check:travel
```

也可以直接访问：

```text
GET /api/v1/travel/health
POST /api/v1/travel/query-plan
```

## 前端无法启动

1. 确认 Node.js 版本满足 `package.json` 的 `engines`。
2. 运行 `npm install`。
3. 运行 `npm run type-check` 查看断引用。
4. 运行 `npm run dev` 启动本地服务。
