"""
Streamlit app: 1D Cutting Stock Optimizer for aluminum/metal facade profiles.
"""

import io
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from optimizer import Solution, optimize, recommend

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Profile Cutter — Cutting Stock Optimizer",
    page_icon="✂️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
if "pieces_df" not in st.session_state:
    st.session_state.pieces_df = pd.DataFrame(
        columns=["Length (mm)", "Quantity"]
    ).astype({"Length (mm)": int, "Quantity": int})

if "quick_length" not in st.session_state:
    st.session_state.quick_length = 1000

if "quick_qty" not in st.session_state:
    st.session_state.quick_qty = 1

if "selected_k" not in st.session_state:
    st.session_state.selected_k = None  # index into solutions list for detail view

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
EXAMPLE_PIECES = [(1000, 4), (450, 3), (1800, 6), (2200, 2)]

ADVANCED_EXAMPLE_PIECES = [
    (400,  8),
    (550,  15),
    (720,  12),
    (875,  6),
    (1050, 20),
    (1200, 9),
    (1380, 14),
    (1500, 11),
    (1680, 7),
    (1920, 18),
    (2100, 5),
    (2250, 10),
    (2400, 3),
    (2500, 8),
]


def df_to_pieces(df: pd.DataFrame) -> list[tuple[int, int]]:
    pieces = []
    for _, row in df.iterrows():
        try:
            l = int(row["Length (mm)"])
            q = int(row["Quantity"])
            if l > 0 and q > 0:
                pieces.append((l, q))
        except (ValueError, TypeError):
            pass
    return pieces


def pieces_df_valid(df: pd.DataFrame) -> bool:
    if df.empty:
        return False
    for _, row in df.iterrows():
        try:
            if int(row["Length (mm)"]) <= 0 or int(row["Quantity"]) <= 0:
                return False
        except (ValueError, TypeError):
            return False
    return True


def fmt(n: int | float) -> str:
    return f"{n:,.0f}"


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def _distinct_colors(n: int) -> list[str]:
    palette = [
        "#4C78A8", "#F58518", "#54A24B", "#E45756", "#B279A2",
        "#9D755D", "#EECA3B", "#72B7B2", "#FF9DA6", "#BAB0AC",
    ]
    colors = []
    for i in range(n):
        colors.append(palette[i % len(palette)])
    return colors


def build_cutting_chart(solution: Solution, kerf: int) -> go.Figure:
    plan = solution.cutting_plan  # list of (stock_length, [pieces])

    # Map each unique piece length to a color
    all_lengths = sorted(set(p for _, pieces in plan for p in pieces))
    colors = _distinct_colors(len(all_lengths))
    color_map = dict(zip(all_lengths, colors))

    fig = go.Figure()
    legend_added: set[int] = set()

    for bar_idx, (stock_len, pieces) in enumerate(plan):
        label = f"Bar {bar_idx + 1} ({fmt(stock_len)} mm)"
        x_offset = 0

        for piece_idx, piece_len in enumerate(pieces):
            show_legend = piece_len not in legend_added
            if show_legend:
                legend_added.add(piece_len)

            fig.add_trace(
                go.Bar(
                    name=f"{fmt(piece_len)} mm",
                    x=[piece_len],
                    y=[label],
                    orientation="h",
                    marker_color=color_map[piece_len],
                    showlegend=show_legend,
                    legendgroup=str(piece_len),
                    hovertemplate=(
                        f"Piece: {fmt(piece_len)} mm<br>"
                        f"Bar: {label}<extra></extra>"
                    ),
                    base=x_offset,
                )
            )
            x_offset += piece_len

            # Draw kerf gap as a thin dark segment
            if kerf > 0 and piece_idx < len(pieces) - 1:
                fig.add_trace(
                    go.Bar(
                        name="Kerf",
                        x=[kerf],
                        y=[label],
                        orientation="h",
                        marker_color="#333333",
                        showlegend=(bar_idx == 0 and piece_len == pieces[0]),
                        legendgroup="kerf",
                        hoverinfo="skip",
                        base=x_offset,
                    )
                )
                x_offset += kerf

        # Waste segment
        waste = stock_len - x_offset
        if waste > 0:
            fig.add_trace(
                go.Bar(
                    name="Waste",
                    x=[waste],
                    y=[label],
                    orientation="h",
                    marker_color="#D3D3D3",
                    marker_pattern_shape="/",
                    showlegend=(bar_idx == 0),
                    legendgroup="waste",
                    hovertemplate=(
                        f"Waste: {fmt(waste)} mm<br>"
                        f"Bar: {label}<extra></extra>"
                    ),
                    base=x_offset,
                )
            )

    max_stock = max(sl for sl, _ in plan)
    fig.update_layout(
        barmode="stack",
        xaxis=dict(title="Length (mm)", range=[0, max_stock * 1.02]),
        yaxis=dict(title="", autorange="reversed"),
        height=max(300, 50 + 40 * len(plan)),
        margin=dict(l=120, r=20, t=30, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        plot_bgcolor="#FAFAFA",
    )
    return fig


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def solution_to_excel(solution: Solution, input_pieces: list[tuple[int, int]]) -> bytes:
    """
    Build an Excel workbook with three sections on one sheet:

    Section 1 — Input Materials
        Length (mm) | Quantity | Total Length (mm)

    [4 empty rows gap]

    Section 2 — Cutting List
        Bar | Stock Length (mm) | Pieces (mm) | Piece Count | Waste (mm) | Utilization (%)

    [4 empty rows gap]

    Section 3 — List of Order
        Qty to Order | Stock Length (mm)
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Cutting Plan"

    # ── Style helpers ──────────────────────────────────────────────────────
    header_font   = Font(bold=True, color="FFFFFF", size=11)
    header_fill_0 = PatternFill("solid", fgColor="375623")   # dark green
    header_fill_1 = PatternFill("solid", fgColor="1F4E79")   # dark blue
    header_fill_2 = PatternFill("solid", fgColor="833333")   # dark red
    section_font  = Font(bold=True, size=13)
    thin_side     = Side(style="thin", color="BBBBBB")
    thin_border   = Border(left=thin_side, right=thin_side,
                           top=thin_side, bottom=thin_side)
    center        = Alignment(horizontal="center", vertical="center")

    def style_header_row(row, col_start, col_end, fill):
        for c in range(col_start, col_end + 1):
            cell = ws.cell(row=row, column=c)
            cell.font      = header_font
            cell.fill      = fill
            cell.alignment = center
            cell.border    = thin_border

    def style_data_row(row, col_start, col_end, shade=False):
        bg = PatternFill("solid", fgColor="EAF0F8") if shade else PatternFill("solid", fgColor="FFFFFF")
        for c in range(col_start, col_end + 1):
            cell = ws.cell(row=row, column=c)
            cell.fill      = bg
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border    = thin_border

    row = 1

    # ── Section 1: Input Materials ─────────────────────────────────────────
    ws.cell(row=row, column=1, value="Input Materials").font = section_font
    row += 1

    inp_headers = ["Length (mm)", "Quantity", "Total Length (mm)"]
    for c, h in enumerate(inp_headers, 1):
        ws.cell(row=row, column=c, value=h)
    style_header_row(row, 1, len(inp_headers), header_fill_0)
    row += 1

    sorted_pieces = sorted(input_pieces, key=lambda x: x[0])
    for shade_idx, (length, qty) in enumerate(sorted_pieces, 1):
        ws.cell(row=row, column=1, value=length)
        ws.cell(row=row, column=2, value=qty)
        ws.cell(row=row, column=3, value=length * qty)
        style_data_row(row, 1, len(inp_headers), shade=(shade_idx % 2 == 0))
        row += 1

    # Totals row
    total_qty = sum(q for _, q in input_pieces)
    total_len = sum(l * q for l, q in input_pieces)
    totals_font = Font(bold=True)
    ws.cell(row=row, column=1, value="Total").font = totals_font
    ws.cell(row=row, column=2, value=total_qty).font = totals_font
    ws.cell(row=row, column=3, value=total_len).font = totals_font
    style_data_row(row, 1, len(inp_headers))
    for c in range(1, len(inp_headers) + 1):
        ws.cell(row=row, column=c).font = totals_font
    row += 1

    # ── Gap ────────────────────────────────────────────────────────────────
    row += 4

    # ── Section 2: Cutting List ────────────────────────────────────────────
    ws.cell(row=row, column=1, value="Cutting List").font = section_font
    row += 1

    cut_headers = ["Bar", "Stock Length (mm)", "Pieces (mm)",
                   "Piece Count", "Waste (mm)", "Utilization (%)"]
    for c, h in enumerate(cut_headers, 1):
        ws.cell(row=row, column=c, value=h)
    style_header_row(row, 1, len(cut_headers), header_fill_1)
    row += 1

    for bar_idx, (stock_len, pieces) in enumerate(solution.cutting_plan, 1):
        used       = sum(pieces)
        waste      = stock_len - used
        util       = round(used / stock_len * 100, 1)
        pieces_str = " | ".join(str(p) for p in sorted(pieces, reverse=True))
        values = [bar_idx, stock_len, pieces_str, len(pieces), waste, util]
        for c, v in enumerate(values, 1):
            ws.cell(row=row, column=c, value=v)
        style_data_row(row, 1, len(cut_headers), shade=(bar_idx % 2 == 0))
        row += 1

    # ── Gap ────────────────────────────────────────────────────────────────
    row += 4

    # ── Section 3: List of Order ───────────────────────────────────────────
    ws.cell(row=row, column=1, value="List of Order").font = section_font
    row += 1

    ord_headers = ["Qty to Order", "Stock Length (mm)"]
    for c, h in enumerate(ord_headers, 1):
        ws.cell(row=row, column=c, value=h)
    style_header_row(row, 1, len(ord_headers), header_fill_2)
    row += 1

    order: dict[int, int] = {}
    for stock_len, _ in solution.cutting_plan:
        order[stock_len] = order.get(stock_len, 0) + 1

    for shade_idx, (stock_len, qty) in enumerate(sorted(order.items()), 1):
        ws.cell(row=row, column=1, value=qty)
        ws.cell(row=row, column=2, value=stock_len)
        style_data_row(row, 1, 2, shade=(shade_idx % 2 == 0))
        row += 1

    # ── Column widths ──────────────────────────────────────────────────────
    col_widths = [6, 20, 48, 13, 13, 16]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Detailed result view
# ---------------------------------------------------------------------------

def show_detail_view(solution: Solution, kerf: int, key_prefix: str = ""):
    # Order summary — editable quantity
    order_data = {}
    for sl, count in zip(solution.stock_lengths, solution.bar_counts):
        order_data.setdefault(sl, 0)
        order_data[sl] += count

    order_df = pd.DataFrame(
        [{"Stock Length (mm)": sl, "Quantity to Order": cnt}
         for sl, cnt in order_data.items()]
    )

    st.subheader("Order Summary")
    st.caption(
        "You can increase the quantity for a buffer — totals update live."
    )

    edited_order = st.data_editor(
        order_df,
        use_container_width=True,
        num_rows="fixed",
        disabled=["Stock Length (mm)"],
        column_config={
            "Stock Length (mm)": st.column_config.NumberColumn(format="%d mm"),
            "Quantity to Order": st.column_config.NumberColumn(min_value=1, step=1),
        },
        key=f"{key_prefix}_order_editor",
    )

    # Recompute totals based on edited quantities
    total_ordered_edited = int(
        sum(
            row["Stock Length (mm)"] * row["Quantity to Order"]
            for _, row in edited_order.iterrows()
        )
    )
    total_used = solution.total_used_mm
    waste_edited = total_ordered_edited - total_used
    util_edited = (total_used / total_ordered_edited * 100) if total_ordered_edited > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Ordered", f"{fmt(total_ordered_edited)} mm  ({total_ordered_edited/1000:.2f} m)")
    col2.metric("Total Used", f"{fmt(total_used)} mm")
    col3.metric(
        "Waste",
        f"{fmt(waste_edited)} mm ({waste_edited / total_ordered_edited * 100:.1f}%)" if total_ordered_edited else "—",
    )

    st.subheader("Cutting Plan")
    fig = build_cutting_chart(solution, kerf)
    st.plotly_chart(fig, use_container_width=True)

    input_pieces = df_to_pieces(st.session_state.pieces_df)
    excel_data = solution_to_excel(solution, input_pieces)
    st.download_button(
        label="⬇ Download cutting plan as Excel",
        data=excel_data,
        file_name="cutting_plan.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key_prefix}_dl",
    )


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

st.title("✂️ Profile Cutter — Cutting Stock Optimizer")
st.markdown(
    "Enter the aluminum or metal facade profile pieces you need; "
    "the optimizer finds the stock length(s) to order that minimize "
    "material waste while keeping your SKU count low."
)

st.markdown("""
<style>
  .marquee-bg-wrapper {
    position: fixed;
    top: 50%;
    left: 0;
    width: 100%;
    overflow: hidden;
    transform: translateY(-50%);
    z-index: 0;
    pointer-events: none;
    opacity: 0.055;
  }
  .marquee-bg-track {
    display: flex;
    width: max-content;
    animation: marquee-scroll 30s linear infinite;
  }
  @keyframes marquee-scroll {
    from { transform: translateX(0); }
    to   { transform: translateX(-50%); }
  }
  .marquee-bg-item {
    font-size: 80px;
    font-weight: 900;
    text-transform: uppercase;
    white-space: nowrap;
    padding-right: 60px;
    font-family: Arial Black, sans-serif;
    color: #111;
  }
  .marquee-bg-item span {
    color: #e30613;
  }
</style>
<div class="marquee-bg-wrapper">
  <div class="marquee-bg-track">
    <div class="marquee-bg-item">Work on <span>Progress</span> &nbsp;•&nbsp; </div>
    <div class="marquee-bg-item">Work on <span>Progress</span> &nbsp;•&nbsp; </div>
    <div class="marquee-bg-item">Work on <span>Progress</span> &nbsp;•&nbsp; </div>
    <div class="marquee-bg-item">Work on <span>Progress</span> &nbsp;•&nbsp; </div>
    <div class="marquee-bg-item">Work on <span>Progress</span> &nbsp;•&nbsp; </div>
    <div class="marquee-bg-item">Work on <span>Progress</span> &nbsp;•&nbsp; </div>
    <div class="marquee-bg-item">Work on <span>Progress</span> &nbsp;•&nbsp; </div>
    <div class="marquee-bg-item">Work on <span>Progress</span> &nbsp;•&nbsp; </div>
  </div>
</div>
""", unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# 1. Required pieces
# ---------------------------------------------------------------------------
st.header("Required Pieces")

col_qa, col_qb, col_qc = st.columns([2, 2, 1])
with col_qa:
    q_len = st.number_input(
        "Length (mm)",
        min_value=1,
        max_value=7500,
        value=st.session_state.quick_length,
        step=10,
        key="qi_length",
    )
with col_qb:
    q_qty = st.number_input(
        "Quantity",
        min_value=1,
        max_value=500,
        value=st.session_state.quick_qty,
        step=1,
        key="qi_qty",
    )
with col_qc:
    st.write("")
    st.write("")
    if st.button("Add", use_container_width=True):
        new_row = pd.DataFrame(
            [{"Length (mm)": int(q_len), "Quantity": int(q_qty)}]
        )
        existing = st.session_state.pieces_df
        # Merge: if same length exists, add quantities
        match = existing["Length (mm)"] == int(q_len)
        if match.any():
            existing.loc[match, "Quantity"] += int(q_qty)
            st.session_state.pieces_df = existing.reset_index(drop=True)
        else:
            st.session_state.pieces_df = pd.concat(
                [existing, new_row], ignore_index=True
            ).astype({"Length (mm)": int, "Quantity": int})
        st.rerun()

btn_col1, btn_col2, btn_col3 = st.columns([1, 2, 5])
with btn_col1:
    if st.button("Load example"):
        st.session_state.pieces_df = pd.DataFrame(
            [{"Length (mm)": l, "Quantity": q} for l, q in EXAMPLE_PIECES]
        ).astype({"Length (mm)": int, "Quantity": int})
        st.rerun()
with btn_col2:
    if st.button("Load advanced example"):
        st.session_state.pieces_df = pd.DataFrame(
            [{"Length (mm)": l, "Quantity": q} for l, q in ADVANCED_EXAMPLE_PIECES]
        ).astype({"Length (mm)": int, "Quantity": int})
        st.rerun()
with btn_col3:
    if st.button("Clear all"):
        st.session_state.pieces_df = pd.DataFrame(
            columns=["Length (mm)", "Quantity"]
        ).astype({"Length (mm)": int, "Quantity": int})
        st.session_state.selected_k = None
        st.rerun()

# Summary line
if not st.session_state.pieces_df.empty:
    valid_df = st.session_state.pieces_df[
        (st.session_state.pieces_df["Length (mm)"] > 0) &
        (st.session_state.pieces_df["Quantity"] > 0)
    ]
    total_count = int(valid_df["Quantity"].sum()) if not valid_df.empty else 0
    total_length_mm = int((valid_df["Length (mm)"] * valid_df["Quantity"]).sum()) if not valid_df.empty else 0
    st.caption(
        f"**{total_count}** pieces · "
        f"**{fmt(total_length_mm)} mm** total ({total_length_mm/1000:.2f} m)"
    )

edited_df = st.data_editor(
    st.session_state.pieces_df,
    use_container_width=True,
    num_rows="dynamic",
    column_config={
        "Length (mm)": st.column_config.NumberColumn(
            "Length (mm)", min_value=1, max_value=7500, step=1, required=True
        ),
        "Quantity": st.column_config.NumberColumn(
            "Quantity", min_value=1, max_value=500, step=1, required=True
        ),
    },
    key="piece_editor",
)
# Sync edits back to session state
if not edited_df.equals(st.session_state.pieces_df):
    st.session_state.pieces_df = edited_df.copy()

st.divider()

# ---------------------------------------------------------------------------
# 2. Settings
# ---------------------------------------------------------------------------
st.header("Settings")

set_col1, set_col2, set_col3 = st.columns(3)
with set_col1:
    max_stock = st.number_input(
        "Max stock length (mm)",
        min_value=500,
        max_value=7500,
        value=4000,
        step=100,
    )
with set_col2:
    mode_options = ["Auto", "1", "2", "3"]
    mode = st.selectbox(
        "Max distinct stock lengths",
        options=mode_options,
        index=0,
        help="Auto runs k=1,2,3 and recommends the best trade-off.",
    )

with st.expander("Advanced"):
    adv1, adv2, adv3 = st.columns(3)
    with adv1:
        kerf = st.number_input("Saw kerf (mm)", min_value=0, max_value=10, value=4, step=1)
    with adv2:
        penalty = st.number_input(
            "Distinct-length penalty (%)",
            min_value=0.0,
            max_value=20.0,
            value=1.5,
            step=0.5,
            help="Extra utilization required to justify adding one more distinct stock length.",
        )
    with adv3:
        time_limit = st.number_input(
            "Solver time limit (s)",
            min_value=5,
            max_value=300,
            value=30,
            step=5,
        )

st.divider()

# ---------------------------------------------------------------------------
# 3. Optimize button
# ---------------------------------------------------------------------------
pieces_valid = pieces_df_valid(st.session_state.pieces_df)

current_pieces = df_to_pieces(st.session_state.pieces_df)
max_piece = max((l for l, _ in current_pieces), default=0)
pieces_fit = max_piece <= max_stock

if not pieces_fit and current_pieces:
    st.warning(
        f"Longest piece ({fmt(max_piece)} mm) exceeds max stock length ({fmt(max_stock)} mm). "
        "Increase max stock length."
    )

run_disabled = not pieces_valid or not pieces_fit

if st.button(
    "Optimize",
    type="primary",
    disabled=run_disabled,
    use_container_width=False,
):
    with st.spinner("CP-SAT solver running…"):
        t0 = time.monotonic()
        try:
            if mode == "Auto":
                solutions = recommend(
                    current_pieces,
                    max_stock_length=int(max_stock),
                    kerf=int(kerf),
                    distinct_penalty_pct=float(penalty),
                    time_limit_s=float(time_limit),
                )
                st.session_state.solutions = solutions
                st.session_state.run_mode = "auto"
            else:
                k = int(mode)
                sol = optimize(
                    current_pieces,
                    max_stock_length=int(max_stock),
                    kerf=int(kerf),
                    max_distinct_lengths=k,
                    time_limit_s=float(time_limit),
                )
                st.session_state.solutions = [sol]
                st.session_state.run_mode = "fixed"
            st.session_state.selected_k = 0
        except Exception as e:
            st.error(f"Solver error: {e}")
            st.session_state.solutions = []
        st.session_state.solve_time = time.monotonic() - t0

# ---------------------------------------------------------------------------
# 4. Results
# ---------------------------------------------------------------------------

if not st.session_state.get("solutions"):
    if pieces_valid:
        st.info("Configure your pieces and settings, then click **Optimize**.")
    else:
        st.info("Add pieces above to get started.")
else:
    solutions: list[Solution] = st.session_state.solutions
    run_mode = st.session_state.get("run_mode", "fixed")
    solve_time = st.session_state.get("solve_time", 0)

    st.header("Results")
    st.caption(f"Solved in {solve_time:.1f} s")

    if run_mode == "auto" and len(solutions) > 1:
        # Show recommended result directly
        recommended = solutions[0]
        lengths_str = ", ".join(f"{fmt(l)} mm" for l in recommended.stock_lengths)
        st.subheader(
            f"Recommended — Stock: {lengths_str}  —  "
            f"Utilization: {recommended.utilization_pct:.1f}%"
        )
        show_detail_view(recommended, int(kerf), key_prefix="auto_rec")

        # Comparison cards in a collapsible expander
        with st.expander("Compare k=1 / k=2 / k=3 options"):
            selected_idx = st.session_state.get("selected_k", 0)
            card_cols = st.columns(len(solutions))

            for idx, (col, sol) in enumerate(zip(card_cols, solutions)):
                with col:
                    is_recommended = idx == 0
                    is_selected = idx == selected_idx
                    tag = " ⭐ Recommended" if is_recommended else ""
                    with st.container(border=True):
                        st.markdown(f"**k = {sol.distinct_count}{tag}**")
                        st.metric("Utilization", f"{sol.utilization_pct:.1f}%")
                        st.metric("Distinct SKUs", sol.distinct_count)
                        st.metric("Total bars", sum(sol.bar_counts))
                        st.metric("Waste", f"{fmt(sol.total_waste_mm)} mm")
                        lengths_str_c = ", ".join(f"{fmt(l)} mm" for l in sol.stock_lengths)
                        st.caption(f"Stock: {lengths_str_c}")
                        if st.button(
                            "View details" if not is_selected else "Showing details",
                            key=f"card_btn_{idx}",
                            disabled=is_selected,
                            use_container_width=True,
                        ):
                            st.session_state.selected_k = idx
                            st.rerun()

            if selected_idx != 0:
                st.divider()
                selected_sol = solutions[selected_idx]
                lengths_str_s = ", ".join(f"{fmt(l)} mm" for l in selected_sol.stock_lengths)
                st.subheader(
                    f"k = {selected_sol.distinct_count}  —  Stock: {lengths_str_s}  —  "
                    f"Utilization: {selected_sol.utilization_pct:.1f}%"
                )
                show_detail_view(selected_sol, int(kerf), key_prefix=f"detail_{selected_idx}")

    else:
        # Single solution
        sol = solutions[0]
        lengths_str = ", ".join(f"{fmt(l)} mm" for l in sol.stock_lengths)
        st.subheader(
            f"k = {sol.distinct_count}  —  Stock: {lengths_str}  —  "
            f"Utilization: {sol.utilization_pct:.1f}%"
        )
        show_detail_view(sol, int(kerf), key_prefix="single")

    st.divider()
    if st.button("Start over for another profile", use_container_width=False):
        st.session_state.pieces_df = pd.DataFrame(
            columns=["Length (mm)", "Quantity"]
        ).astype({"Length (mm)": int, "Quantity": int})
        st.session_state.solutions = []
        st.session_state.selected_k = None
        st.rerun()
