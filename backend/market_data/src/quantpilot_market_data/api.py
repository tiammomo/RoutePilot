from __future__ import annotations

from fastapi import FastAPI, HTTPException

from quantpilot_market_data.models import BatchQuoteRequest, BatchQuoteResponse, RealtimeQuote
from quantpilot_market_data.providers.eastmoney import EastMoneyClient, EastMoneyError


def create_app() -> FastAPI:
    app = FastAPI(
        title="QuantPilot Market Data API",
        description="QuantPilot 量化分析 Agent 的市场数据后端",
        version="0.1.0",
    )
    client = EastMoneyClient()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/quotes/realtime/{symbol}", response_model=RealtimeQuote)
    async def get_realtime_quote(symbol: str) -> RealtimeQuote:
        try:
            return await client.get_realtime_quote(symbol)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.post("/api/v1/quotes/realtime", response_model=BatchQuoteResponse)
    async def get_realtime_quotes(request: BatchQuoteRequest) -> BatchQuoteResponse:
        try:
            quotes = await client.get_realtime_quotes(request.symbols)
            return BatchQuoteResponse(quotes=quotes)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    return app


app = create_app()
