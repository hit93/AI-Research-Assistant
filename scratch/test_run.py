import sys
sys.path.insert(0, ".")
from src.graphs.graph import run_research

def on_prog(status, detail):
    print(f"[{status}] {detail}", flush=True)

res = run_research("quantum computing", research_mode="quick", on_progress=on_prog, use_cache=False)
print("Done!", flush=True)
print(f"Sources count: {len(res.sources)}", flush=True)
print(f"Synthesis sections: {len(res.synthesis)}", flush=True)
if res.verification:
    print(f"Verification score: {res.verification.overall_score}", flush=True)
print(f"Errors: {res.errors}", flush=True)
