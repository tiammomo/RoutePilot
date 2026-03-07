# API Reference

所有业务接口默认前缀为 `/api`。

## Health

- `GET /api/health`
- `GET /api/health/llm`
- `GET /api/ready`
- `GET /api/live`

## Chat

- `POST /api/chat/stream`

请求体：

```json
{
  "message": "推荐一个周末短途城市",
  "session_id": "optional",
  "mode": "direct|react|plan"
}
```

## Session

- `POST /api/session/new`
- `GET /api/sessions`
- `DELETE /api/session/{session_id}`
- `PUT /api/session/{session_id}/name`
- `PUT /api/session/{session_id}/model`
- `GET /api/session/{session_id}/model`
- `POST /api/clear/{session_id}`
- `POST /api/clear?session_id=...`

## Model

- `GET /api/models`
- `GET /api/models/{model_id}`

## City

- `GET /api/cities`
- `GET /api/cities/{city_id}`
- `GET /api/cities/{city_id}/attractions`
- `GET /api/regions`
- `GET /api/tags`

## API 文档页面

- `GET /docs`
- `GET /rapidoc`
- `GET /redoc`
