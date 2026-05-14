import asyncio, json
import httpx

BASE = "http://localhost:8000"

async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=120.0) as client:
        email = "copilot_admin2@example.com"
        password = "TestSecret123!"
        await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "full_name": "Copilot Admin2",
            "role": "admin",
        })
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        async with client.stream("POST", "/api/v1/chat/stream", json={"message": "Donne moi les informations de EMP0001"}, headers=headers) as resp:
            print("STATUS", resp.status_code)
            async for line in resp.aiter_lines():
                if line:
                    print("LINE", line[:200])

asyncio.run(main())
