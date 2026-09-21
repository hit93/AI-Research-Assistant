import sys
sys.path.insert(0, ".")
from config.settings import settings
from langchain_google_genai import ChatGoogleGenerativeAI

models = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

api_key = settings.GEMINI_API_KEY
print("====================================================================", flush=True)
print(f"GOOGLE AI STUDIO API QUOTA CHECK (Key: {api_key[:6]}...{api_key[-4:]})", flush=True)
print("====================================================================", flush=True)

for m in models:
    try:
        llm = ChatGoogleGenerativeAI(
            model=m,
            google_api_key=api_key,
            max_tokens=5,
            max_retries=0,
        )
        resp = llm.invoke("ping")
        txt = resp.content.strip().replace("\n", " ") if isinstance(resp.content, str) else str(resp.content)
        print(f"[ACTIVE]      {m:<24} -> OK! Response: '{txt[:25]}'", flush=True)
    except Exception as e:
        err = str(e)
        if "RESOURCE_EXHAUSTED" in err or "429" in err:
            # Parse daily limit or rate limit
            if "GenerateRequestsPerDay" in err or "free_tier_requests" in err:
                print(f"[EXHAUSTED]   {m:<24} -> 429 Daily Free-Tier Cap Reached (Limit: 20 RPD exhausted)", flush=True)
            else:
                print(f"[RATE-LIMIT]  {m:<24} -> 429 RPM Rate limit / cooldown", flush=True)
        elif "NOT_FOUND" in err or "404" in err:
            if "no longer available" in err:
                print(f"[DEPRECATED]  {m:<24} -> 404 (Deprecated for new users)", flush=True)
            else:
                print(f"[NOT FOUND]   {m:<24} -> 404 (Model ID does not exist)", flush=True)
        else:
            print(f"[ERROR]       {m:<24} -> {err[:80]}", flush=True)

print("====================================================================", flush=True)
