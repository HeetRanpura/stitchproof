# Tinker cost of this build

From `tinker billing usage` for 2026-10-17 (estimated gross usage cost, rate-card prices; may change slightly when the day's invoice is finalised).

| Model | Use | US$ |
| --- | --- | --- |
| Qwen/Qwen3.5-4B | training (v1, 1 epoch + val passes) | 1.018 |
| Qwen/Qwen3.5-4B | sampling (baselines A, C; fine-tuned D; equivalence check) | 0.359 |
| openai/gpt-oss-120b | training-data rewrites + baseline B | 0.041 |
| Qwen/Qwen3.5-397B-A17B | training-data rewrites | 0.084 |
| moonshotai/Kimi-K2.6 | OOD eval set writing | 0.099 |
| storage | checkpoints | 0.017 |
| **Total** | | **1.619** |
