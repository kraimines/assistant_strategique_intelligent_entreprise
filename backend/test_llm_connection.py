import asyncio
from app.core.llm import test_llm_connection

async def main():
    result = await test_llm_connection()
    print(result)

asyncio.run(main())
