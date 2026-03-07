"""
================================================================================
API 文档路由模块 - RapiDoc + ReDoc 集成
================================================================================

提供 RapiDoc 和 ReDoc 两种 API 文档界面。

端点说明:
    GET /docs     - API 文档选择页面
    GET /rapidoc  - RapiDoc 页面（支持在线测试）
    GET /redoc    - ReDoc 页面（纯文档展示）

使用示例:
    http://localhost:8000/docs      # 文档选择页面
    http://localhost:8000/rapidoc   # RapiDoc（含在线测试）
    http://localhost:8000/redoc     # ReDoc（纯展示）
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


# =============================================================================
# RapiDoc 页面（支持在线测试）
# =============================================================================

RAPIDOC_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RapiDoc - ShuaiTravelAgent API</title>
    <!-- RapiDoc Web Component -->
    <script type="module" src="https://unpkg.com/rapidoc/dist/rapidoc-min.js"></script>
    <style>
        /* 自定义滚动条样式 */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: #1a202c;
        }
        ::-webkit-scrollbar-thumb {
            background: #4a5568;
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #667eea;
        }
        body { margin: 0; padding: 0; }
        rapidoc { height: 100vh; --primary: #667eea; }

        /* 减小间距 */
        .nav-logo { padding: 8px 12px !important; }
        .nav-bar { padding: 4px 12px !important; }
        .api-title { margin: 8px 0 !important; padding: 0 12px !important; }
        .endpoint { padding: 8px 12px !important; margin: 4px 0 !important; }
        .method-badge { padding: 2px 8px !important; font-size: 11px !important; }
        .path-text { font-size: 13px !important; }
        .tag-group { margin-bottom: 12px !important; }
        .tag-header { padding: 8px 12px !important; }
        .section-title { padding: 8px 12px !important; font-size: 14px !important; }
        .response-status { padding: 4px 8px !important; }
        .code-block { padding: 8px 12px !important; font-size: 12px !important; }
        .param-row { padding: 6px 12px !important; }
        .param-name { font-size: 13px !important; }
        .param-desc { font-size: 12px !important; }

        /* SSE 测试面板样式 */
        .sse-panel {
            position: fixed;
            right: 20px;
            bottom: 20px;
            width: 400px;
            max-height: 500px;
            background: #1a202c;
            border: 1px solid #4a5568;
            border-radius: 12px;
            padding: 16px;
            z-index: 1000;
            box-shadow: 0 10px 40px rgba(0,0,0,0.4);
        }
        .sse-panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 12px;
            border-bottom: 1px solid #4a5568;
        }
        .sse-panel-title {
            color: #fff;
            font-size: 14px;
            font-weight: bold;
        }
        .sse-close {
            background: none;
            border: none;
            color: #a0aec0;
            font-size: 20px;
            cursor: pointer;
        }
        .sse-close:hover { color: #fff; }
        .sse-input {
            width: 100%;
            padding: 10px 12px;
            background: #2d3748;
            border: 1px solid #4a5568;
            border-radius: 8px;
            color: #fff;
            font-size: 14px;
            margin-bottom: 12px;
            resize: vertical;
        }
        .sse-input:focus {
            outline: none;
            border-color: #667eea;
        }
        .sse-btn {
            width: 100%;
            padding: 10px 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 8px;
            color: #fff;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            margin-bottom: 12px;
        }
        .sse-btn:hover { opacity: 0.9; }
        .sse-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .sse-output {
            background: #2d3748;
            border-radius: 8px;
            padding: 12px;
            max-height: 250px;
            overflow-y: auto;
            font-family: Monaco, Consolas, monospace;
            font-size: 12px;
            color: #68d391;
            white-space: pre-wrap;
            word-break: break-all;
        }
        .sse-output.error { color: #fc8181; }
        .sse-output .label { color: #667eea; }
        .sse-output .content { color: #fff; }
        .sse-toggle {
            position: fixed;
            right: 20px;
            bottom: 20px;
            width: 50px;
            height: 50px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 50%;
            color: #fff;
            font-size: 20px;
            cursor: pointer;
            z-index: 1001;
            box-shadow: 0 4px 20px rgba(102, 126, 234, 0.4);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .sse-toggle:hover { transform: scale(1.1); }
        .sse-hidden { display: none !important; }
    </style>
</head>
<body>
    <rapi-doc
        spec-url="/openapi.json"
        theme="dark"
        render-style="read"
        show-header="true"
        show-info="true"
        show-side-nav="true"
        allow-try="true"
        allow-authentication="true"
        allow-server-selection="false"
        allow-api-list-style-selection="false"
        show-components="true"
        navbar-always-visible="true"
        default-schema-tab="response"
        expand-response-examples="all"
        fill-request-examples="true"
        heading-text="API 文档"
        nav-item-spacing="compact"
        schema-style="table"
    >
        <div slot="nav-logo" style="padding: 6px 12px; display: flex; align-items: center; gap: 8px; cursor: pointer;" onclick="window.location.reload()">
            <span style="font-size: 20px;">🧪</span>
            <span style="font-weight: bold; font-size: 14px; color: #fff;">RapiDoc</span>
        </div>
    </rapi-doc>

    <!-- SSE 测试面板 -->
    <button class="sse-toggle" onclick="toggleSSEPanel()" title="SSE 流式测试">📡</button>

    <div class="sse-panel sse-hidden" id="ssePanel">
        <div class="sse-panel-header">
            <span class="sse-panel-title">📡 SSE 流式测试</span>
            <button class="sse-close" onclick="toggleSSEPanel()">×</button>
        </div>
        <textarea class="sse-input" id="sseMessage" rows="3" placeholder="输入消息内容，例如：北京三日游怎么安排？"></textarea>
        <input class="sse-input" id="sseSessionId" type="text" placeholder="可选：会话 ID" style="margin-bottom: 8px;">
        <button class="sse-btn" id="sseBtn" onclick="startSSETest()">开始测试</button>
        <div class="sse-output" id="sseOutput">等待输入...</div>
    </div>

    <script>
        let sseController = null;

        function toggleSSEPanel() {
            const panel = document.getElementById('ssePanel');
            const toggle = document.querySelector('.sse-toggle');
            panel.classList.toggle('sse-hidden');
            toggle.classList.toggle('sse-hidden');
        }

        function formatTime() {
            return new Date().toLocaleTimeString('zh-CN', { hour12: false });
        }

        function appendOutput(text, isError = false) {
            const output = document.getElementById('sseOutput');
            const className = isError ? 'sse-output error' : 'sse-output';
            output.innerHTML += `<div><span class="label">[${formatTime()}]</span> <span class="content">${text}</span></div>`;
            output.scrollTop = output.scrollHeight;
        }

        function clearOutput() {
            document.getElementById('sseOutput').innerHTML = '';
        }

        function startSSETest() {
            const message = document.getElementById('sseMessage').value.trim();
            const sessionId = document.getElementById('sseSessionId').value.trim();
            const btn = document.getElementById('sseBtn');

            if (!message) {
                appendOutput('请输入消息内容', true);
                return;
            }

            // 停止之前的连接
            if (sseController) {
                sseController.abort();
            }

            // 禁用按钮
            btn.disabled = true;
            btn.textContent = '测试中...';
            clearOutput();

            // 构建请求
            const url = '/api/chat/stream';
            const data = {
                message: message,
                session_id: sessionId || undefined
            };

            appendOutput('开始连接...');

            // 创建 SSE 连接
            sseController = new AbortController();
            fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
                signal: sseController.signal
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                function read() {
                    return reader.read().then(({ done, value }) => {
                        if (done) {
                            appendOutput('\n[连接关闭]');
                            btn.disabled = false;
                            btn.textContent = '开始测试';
                            return;
                        }

                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        buffer = lines.pop();

                        for (const line of lines) {
                            if (line.startsWith('data: ')) {
                                try {
                                    const json = JSON.parse(line.slice(6));
                                    const type = json.type;
                                    const content = json.content || '';

                                    switch(type) {
                                        case 'session_id':
                                            appendOutput(`会话 ID: ${content}`);
                                            break;
                                        case 'reasoning_start':
                                            appendOutput('\n--- 思考开始 ---');
                                            break;
                                        case 'reasoning_chunk':
                                            appendOutput(content);
                                            break;
                                        case 'reasoning_end':
                                            appendOutput('--- 思考结束 ---\n');
                                            break;
                                        case 'answer_start':
                                            appendOutput('--- 回答 ---\n');
                                            break;
                                        case 'chunk':
                                            appendOutput(content);
                                            break;
                                        case 'done':
                                            appendOutput('\n[完成]');
                                            break;
                                        case 'error':
                                            appendOutput(`错误: ${content}`, true);
                                            break;
                                    }
                                } catch (e) {
                                    // 忽略解析错误
                                }
                            }
                        }

                        return read();
                    });
                }

                return read();
            })
            .catch(err => {
                if (err.name !== 'AbortError') {
                    appendOutput(`请求失败: ${err.message}`, true);
                }
                btn.disabled = false;
                btn.textContent = '开始测试';
            });
        }
    </script>
</body>
</html>
"""


# =============================================================================
# ReDoc 页面（纯文档展示）
# =============================================================================

REDOC_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ReDoc - ShuaiTravelAgent API</title>
    <!-- ReDoc -->
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
        body { margin: 0; padding: 0; }
    </style>
</head>
<body>
    <redoc
        spec-url='/openapi.json'
        theme='{
            "colors": {
                "primary": {
                    "main": "#667eea"
                },
                "success": {
                    "main": "#52c41a"
                },
                "warning": {
                    "main": "#faad14"
                },
                "error": {
                    "main": "#ff4d4f"
                },
                "text": {
                    "primary": "#2d3748"
                },
                "gray": {
                    "50": "#f7fafc",
                    "100": "#edf2f7",
                    "200": "#e2e8f0",
                    "300": "#cbd5e0",
                    "400": "#a0aec0",
                    "500": "#718096",
                    "600": "#4a5568",
                    "700": "#2d3748",
                    "800": "#1a202c",
                    "900": "#171923"
                }
            },
            "typography": {
                "fontFamily": "Roboto, -apple-system, BlinkMacSystemFont, sans-serif",
                "fontSize": "14px",
                "lineHeight": "1.5",
                "headings": {
                    "fontWeight": "700",
                    "fontFamily": "Montserrat, sans-serif"
                },
                "code": {
                    "fontFamily": "Monaco, Consolas, monospace"
                }
            },
            "sidebar": {
                "backgroundColor": "#f7fafc",
                "textColor": "#2d3748",
                "activeTextColor": "#667eea",
                "borderColor": "#e2e8f0"
            },
            "rightPanel": {
                "backgroundColor": "#2d3748",
                "textColor": "#f7fafc",
                "width": "40%"
            }
        }'
        expand-single-description="true"
        scroll-y-offset="60"
        show-object-schema-types="true"
        disable-search="false"
        hide-loading="false"
        keyboard-shortcuts="true"
    ></redoc>
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
</body>
</html>
"""


# =============================================================================
# 文档选择页面
# =============================================================================

SELECTOR_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API 文档选择 - ShuaiTravelAgent</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }

        .container {
            text-align: center;
            padding: 50px 40px;
            background: white;
            border-radius: 24px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            max-width: 600px;
            width: 90%;
        }

        .logo {
            font-size: 48px;
            margin-bottom: 16px;
        }

        h1 {
            margin-bottom: 12px;
            color: #1a202c;
            font-size: 28px;
            font-weight: 700;
        }

        .subtitle {
            color: #718096;
            font-size: 16px;
            margin-bottom: 40px;
        }

        .btn-group {
            display: flex;
            gap: 20px;
            justify-content: center;
            flex-wrap: wrap;
            margin-bottom: 30px;
        }

        .btn {
            padding: 20px 36px;
            font-size: 16px;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
            color: white;
            font-weight: 600;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
            min-width: 160px;
        }

        .btn:hover {
            transform: translateY(-4px);
            box-shadow: 0 12px 20px rgba(0, 0, 0, 0.15);
        }

        .btn:active {
            transform: translateY(-2px);
        }

        .btn-rapidoc {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }

        .btn-redoc {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }

        .btn-icon {
            font-size: 28px;
        }

        .btn-text small {
            font-weight: 400;
            opacity: 0.9;
            font-size: 13px;
        }

        .description {
            color: #a0aec0;
            font-size: 13px;
            line-height: 1.6;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">🚗</div>
        <h1>ShuaiTravelAgent API</h1>
        <p class="subtitle">智能旅游规划助手 API 文档</p>

        <div class="btn-group">
            <a href="/rapidoc" class="btn btn-rapidoc">
                <span class="btn-icon">🧪</span>
                <span class="btn-text">
                    RapiDoc
                    <small>支持在线测试</small>
                </span>
            </a>
            <a href="/redoc" class="btn btn-redoc">
                <span class="btn-icon">📖</span>
                <span class="btn-text">
                    ReDoc
                    <small>纯文档展示</small>
                </span>
            </a>
        </div>

        <p class="description">
            RapiDoc 提供在线 API 测试功能，ReDoc 提供美观的文档阅读体验
        </p>
    </div>
</body>
</html>
"""


# =============================================================================
# 路由定义
# =============================================================================

@router.get("/docs", include_in_schema=False)
async def docs_selector():
    """
    API 文档选择页面

    提供 RapiDoc 和 ReDoc 两种文档视图选择。

    Returns:
        HTML: 文档选择页面
    """
    return HTMLResponse(content=SELECTOR_HTML)


@router.get("/rapidoc", include_in_schema=False)
async def rapidoc_page():
    """
    RapiDoc API 文档页面

    提供完整的 API 文档和在线测试功能。

    Returns:
        HTML: RapiDoc 页面
    """
    return HTMLResponse(content=RAPIDOC_HTML)


@router.get("/redoc", include_in_schema=False)
async def redoc_page():
    """
    ReDoc API 文档页面

    提供美观的 API 文档展示界面。

    Returns:
        HTML: ReDoc 页面
    """
    return HTMLResponse(content=REDOC_HTML)
