from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("QUANTPILOT_MARKET_HOST", "127.0.0.1")
    port = int(os.getenv("QUANTPILOT_MARKET_PORT", "8010"))
    uvicorn.run(
        "quantpilot_market_data.api:app",
        host=host,
        port=port,
        reload=os.getenv("QUANTPILOT_MARKET_RELOAD", "0") == "1",
    )


if __name__ == "__main__":
    main()
