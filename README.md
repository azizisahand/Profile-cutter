# Profile Cutter — 1D Cutting Stock Optimizer

Optimize how to cut aluminum or metal facade profiles from stock bars to minimize waste and keep your order to a small number of distinct SKU lengths.

## What it does

- You enter the profile pieces you need (length in mm and quantity).
- The CP-SAT solver (Google OR-Tools) finds the optimal stock length(s) to order and the exact cutting plan for each bar.
- **Auto mode** runs k = 1, 2, and 3 distinct stock lengths and recommends the best trade-off between utilization and SKU complexity.
- The cutting plan is visualized as a stacked bar chart and can be exported as CSV.

## Setup

```bash
cd "C:\Users\Sahan\Documents\Projects\Profile-cutter"
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

On macOS/Linux activate with:
```bash
source .venv/bin/activate
```

## Run locally

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Deploy to Streamlit Community Cloud

1. Push this repository to GitHub (exclude `.venv/` — it's in `.gitignore`).
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect your GitHub repo.
3. Set the main file path to `app.py`.
4. Deploy — Streamlit Cloud installs `requirements.txt` automatically.

## Project structure

```
Profile-cutter/
├── app.py           # Streamlit UI
├── optimizer.py     # OR-Tools CP-SAT algorithm
├── requirements.txt
├── README.md
└── .gitignore
```

## Algorithm notes

- **Bin packing** (single stock length): CP-SAT binary variables x[piece][bin] and y[bin], capacity constraint accounts for saw kerf between cuts.
- **k > 1**: CP-SAT assigns each piece to one of k stock length classes and packs within each class; objective minimizes total ordered material.
- **Enumeration**: k=1 steps at 10 mm, k=2 at 50 mm, k=3 at 100 mm over the candidate range to keep runtime sane.
- **Auto recommendation** scores each solution as `utilization% − penalty% × (k−1)` (default penalty 1.5%), so adding a distinct SKU must earn more than 1.5 percentage points of utilization to be recommended.
