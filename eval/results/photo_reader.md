# Gemma 4 photo reader

Model: `gemma4:e4b-it-qat` via Ollama, on this Mac. 12 held-out eval_synth patterns (8 with seeded errors), each rendered as a clean scan and as a photo-like image (rotation, uneven light, noise, JPEG). Rows are matched by row number.

| | Original text | Scan → Gemma | Photo → Gemma |
| --- | --- | --- | --- |
| Lines transcribed exactly | – | 50.3% (81/161) | 42.2% (68/161) |
| Numbers kept | – | 98.9% (357/361) | 98.1% (354/361) |
| Extra numbers introduced | – | 2 | 3 |
| Character similarity (mean) | – | 0.9887 | 0.98 |
| **Errors caught (end to end)** | 100.0% (12/12) | 91.7% (11/12) | 100.0% (12/12) |
| **False alarms (end to end)** | 23.2% (22/95) | 25.3% (24/95) | 22.1% (21/95) |
| Seconds per image (mean) | – | 15.1 | 15.1 |

Example images: `docs/screenshots/photo_reader_scan_example.jpg`, `docs/screenshots/photo_reader_photo_example.jpg`.
