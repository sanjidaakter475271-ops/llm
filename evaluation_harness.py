import json
import os
import time

GOLDEN_TESTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_tests")

def create_sample_golden_tests():
    os.makedirs(GOLDEN_TESTS_DIR, exist_ok=True)
    sample_tests = [
        {
            "id": "test_lm_training",
            "type": "lm",
            "situation": "Request for aircrew training schedule update",
            "expected_keywords": ["reqr", "auth", "info", "nec act"],
            "expected_type": "lm"
        },
        {
            "id": "test_rl_procurement",
            "type": "rl",
            "situation": "Procurement request for 5 printers due to unserviceability",
            "expected_keywords": ["unsvc", "proc", "reqr"],
            "expected_type": "rl"
        }
    ]
    for test in sample_tests:
        path = os.path.join(GOLDEN_TESTS_DIR, f"{test['id']}.json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(test, f, indent=2)

def run_evaluation(generator_fn):
    create_sample_golden_tests()
    results = []
    for fname in os.listdir(GOLDEN_TESTS_DIR):
        if fname.endswith(".json"):
            with open(os.path.join(GOLDEN_TESTS_DIR, fname), "r", encoding="utf-8") as f:
                test_case = json.load(f)
                
            start = time.time()
            # Execute generation simulation / check
            output = generator_fn(test_case["type"], {"situation": test_case["situation"]})
            elapsed = time.time() - start
            
            # Simple metric scoring
            body_str = json.dumps(output.get("body", "")).lower()
            keyword_matches = [kw for kw in test_case["expected_keywords"] if kw.lower() in body_str]
            match_score = len(keyword_matches) / len(test_case["expected_keywords"]) if test_case["expected_keywords"] else 1.0
            
            results.append({
                "test_id": test_case["id"],
                "type": test_case["type"],
                "latency_sec": round(elapsed, 2),
                "match_score": match_score,
                "passed": match_score >= 0.5
            })
    return results

if __name__ == "__main__":
    create_sample_golden_tests()
    print("Golden test harness ready.")
