@echo off
echo Installing LangChain dependencies...

call conda activate agents

pip install langchain>=0.3.0 langchain-core>=0.3.0 langgraph>=0.2.0 langgraph-prebuilt>=0.1.0 langchain-community>=0.3.0 langchain-openai>=0.2.0 langchain-anthropic>=0.3.0

echo.
echo Installation complete!
pause
