import asyncio, json
import httpx

BASE = "http://localhost:8000"

async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=60.0) as client:
        # register + login test admin (idempotent)
        email = "copilot_admin@example.com"
        password = "TestSecret123!"
        await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "full_name": "Copilot Admin",
            "role": "admin",
        })
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        print("LOGIN", r.status_code, r.text[:200])
        r.raise_for_status()
        token = r.json()["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        # call non-streaming chat endpoint for simplicity
        r2 = await client.post("/api/v1/chat", json={"message": "Donne moi les informations de EMP0001"}, headers=headers)
        print("CHAT", r2.status_code)
        print(r2.text[:400])

asyncio.run(main())
