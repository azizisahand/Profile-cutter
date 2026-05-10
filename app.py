"""
Streamlit app: 1D Cutting Stock Optimizer for aluminum/metal facade profiles.
"""

import io
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from optimizer import Solution, optimize, recommend
from translations import T

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
if "lang" not in st.session_state:
    st.session_state.lang = "en"

if "pieces_df" not in st.session_state:
    st.session_state.pieces_df = pd.DataFrame(
        columns=["Length (mm)", "Quantity"]
    ).astype({"Length (mm)": int, "Quantity": int})

if "just_added" not in st.session_state:
    st.session_state.just_added = False

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


def build_cutting_chart(solution: Solution, kerf: int, lang: str = "en") -> go.Figure:
    t = T(lang)
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
                        name=t["chart_kerf"],
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
                    name=t["chart_waste"],
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
    t = T(st.session_state.get("lang", "en"))
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = t["xl_sheet"]

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
    ws.cell(row=row, column=1, value=t["xl_input_title"]).font = section_font
    row += 1

    inp_headers = [t["xl_input_length"], t["xl_input_qty"], t["xl_input_total"]]
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
    ws.cell(row=row, column=1, value=t["xl_input_total_row"]).font = totals_font
    ws.cell(row=row, column=2, value=total_qty).font = totals_font
    ws.cell(row=row, column=3, value=total_len).font = totals_font
    style_data_row(row, 1, len(inp_headers))
    for c in range(1, len(inp_headers) + 1):
        ws.cell(row=row, column=c).font = totals_font
    row += 1

    # ── Gap ────────────────────────────────────────────────────────────────
    row += 4

    # ── Section 2: Cutting List ────────────────────────────────────────────
    ws.cell(row=row, column=1, value=t["xl_cutting_title"]).font = section_font
    row += 1

    cut_headers = [t["xl_cut_bar"], t["xl_cut_stock"], t["xl_cut_pieces"],
                   t["xl_cut_count"], t["xl_cut_waste"], t["xl_cut_util"]]
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
    ws.cell(row=row, column=1, value=t["xl_order_title"]).font = section_font
    row += 1

    ord_headers = [t["xl_order_qty"], t["xl_order_stock"]]
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
    t = T(st.session_state.get("lang", "en"))

    # Order summary — editable quantity
    order_data = {}
    for sl, count in zip(solution.stock_lengths, solution.bar_counts):
        order_data.setdefault(sl, 0)
        order_data[sl] += count

    col_stock = t["col_stock_length"]
    col_qty   = t["col_qty_order"]

    order_df = pd.DataFrame(
        [{col_stock: sl, col_qty: cnt} for sl, cnt in order_data.items()]
    )

    st.subheader(t["subheader_order"])
    st.caption(t["caption_order"])

    edited_order = st.data_editor(
        order_df,
        use_container_width=True,
        num_rows="fixed",
        disabled=[col_stock],
        column_config={
            col_stock: st.column_config.NumberColumn(format="%d mm"),
            col_qty:   st.column_config.NumberColumn(min_value=1, step=1),
        },
        key=f"{key_prefix}_order_editor",
    )

    total_ordered_edited = int(
        sum(row[col_stock] * row[col_qty] for _, row in edited_order.iterrows())
    )
    total_used   = solution.total_used_mm
    waste_edited = total_ordered_edited - total_used

    col1, col2, col3 = st.columns(3)
    col1.metric(t["metric_total_ordered"],
                f"{fmt(total_ordered_edited)} mm  ({total_ordered_edited/1000:.2f} m)")
    col2.metric(t["metric_total_used"], f"{fmt(total_used)} mm")
    col3.metric(
        t["metric_waste"],
        t["metric_waste_val"].format(
            mm=waste_edited,
            pct=waste_edited / total_ordered_edited * 100,
        ) if total_ordered_edited else "—",
    )

    st.subheader(t["subheader_cutting"])
    fig = build_cutting_chart(solution, kerf, lang=st.session_state.get("lang", "en"))
    st.plotly_chart(fig, use_container_width=True)

    input_pieces = df_to_pieces(st.session_state.pieces_df)
    excel_data = solution_to_excel(solution, input_pieces)
    st.download_button(
        label=t["btn_download"],
        data=excel_data,
        file_name="cutting_plan.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key_prefix}_dl",
    )


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

# Language toggle — top right
_title_col, _lang_col = st.columns([9, 1])
with _lang_col:
    _lang_choice = st.selectbox(
        "",
        options=["🇬🇧 EN", "🇩🇪 DE"],
        index=0 if st.session_state.lang == "en" else 1,
        label_visibility="collapsed",
        key="lang_selector",
    )
    st.session_state.lang = "en" if "EN" in _lang_choice else "de"

t = T(st.session_state.lang)

with _title_col:
    st.title(t["title"])
st.markdown(t["subtitle"])

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
st.header(t["section_pieces"])

with st.form("quick_add_form", clear_on_submit=True):
    col_qa, col_qb, col_qc = st.columns([2, 2, 1])
    with col_qa:
        q_len_raw = st.text_input(
            t["col_length"], value="", placeholder="e.g. 1200", key="qi_length"
        )
    with col_qb:
        q_qty_raw = st.text_input(
            t["col_qty"], value="", placeholder="1", key="qi_qty"
        )
    with col_qc:
        st.write("")
        st.write("")
        submitted = st.form_submit_button(t["btn_add"], use_container_width=True)

    if submitted:
        try:
            q_len = int(q_len_raw.strip()) if q_len_raw.strip() else None
            q_qty = int(q_qty_raw.strip()) if q_qty_raw.strip() else 1
        except ValueError:
            q_len, q_qty = None, 1

        if q_len and q_len > 0:
            q_qty = max(q_qty, 1)
            existing = st.session_state.pieces_df
            match = existing["Length (mm)"] == q_len
            if match.any():
                existing.loc[match, "Quantity"] += q_qty
                st.session_state.pieces_df = existing.reset_index(drop=True)
            else:
                st.session_state.pieces_df = pd.concat(
                    [existing, pd.DataFrame([{"Length (mm)": q_len, "Quantity": q_qty}])],
                    ignore_index=True,
                ).astype({"Length (mm)": int, "Quantity": int})
            st.session_state.just_added = True

# Refocus the Length input after a successful add
if st.session_state.just_added:
    st.session_state.just_added = False
    st.components.v1.html("""
    <script>
        setTimeout(function() {
            var inputs = window.parent.document.querySelectorAll(
                '[data-testid="stTextInput"] input'
            );
            if (inputs.length > 0) inputs[0].focus();
        }, 120);
    </script>
    """, height=0)

btn_col1, btn_col2, btn_col3 = st.columns([1, 2, 5])
with btn_col1:
    if st.button(t["btn_load_example"]):
        st.session_state.pieces_df = pd.DataFrame(
            [{"Length (mm)": l, "Quantity": q} for l, q in EXAMPLE_PIECES]
        ).astype({"Length (mm)": int, "Quantity": int})
        st.rerun()
with btn_col2:
    if st.button(t["btn_load_advanced"]):
        st.session_state.pieces_df = pd.DataFrame(
            [{"Length (mm)": l, "Quantity": q} for l, q in ADVANCED_EXAMPLE_PIECES]
        ).astype({"Length (mm)": int, "Quantity": int})
        st.rerun()
with btn_col3:
    if st.button(t["btn_clear"]):
        st.session_state.pieces_df = pd.DataFrame(
            columns=["Length (mm)", "Quantity"]
        ).astype({"Length (mm)": int, "Quantity": int})
        st.session_state.selected_k = None
        st.rerun()

if not st.session_state.pieces_df.empty:
    valid_df = st.session_state.pieces_df[
        (st.session_state.pieces_df["Length (mm)"] > 0) &
        (st.session_state.pieces_df["Quantity"] > 0)
    ]
    total_count     = int(valid_df["Quantity"].sum()) if not valid_df.empty else 0
    total_length_mm = int((valid_df["Length (mm)"] * valid_df["Quantity"]).sum()) if not valid_df.empty else 0
    st.caption(t["caption_pieces"].format(
        count=total_count, mm=fmt(total_length_mm), m=total_length_mm / 1000
    ))

edited_df = st.data_editor(
    st.session_state.pieces_df,
    use_container_width=True,
    num_rows="dynamic",
    column_config={
        "Length (mm)": st.column_config.NumberColumn(
            t["col_length"], min_value=1, max_value=7500, step=1, required=True
        ),
        "Quantity": st.column_config.NumberColumn(
            t["col_qty"], min_value=1, max_value=500, step=1, required=True
        ),
    },
    key="piece_editor",
)
if not edited_df.equals(st.session_state.pieces_df):
    st.session_state.pieces_df = edited_df.copy()

st.divider()

# ---------------------------------------------------------------------------
# 2. Settings
# ---------------------------------------------------------------------------
st.header(t["section_settings"])

set_col1, set_col2, _ = st.columns(3)
with set_col1:
    max_stock = st.number_input(
        t["max_stock_label"], min_value=500, max_value=7500, value=4000, step=100,
    )
with set_col2:
    mode = st.selectbox(
        t["mode_label"], options=["Auto", "1", "2", "3"], index=0, help=t["mode_help"],
    )

with st.expander(t["expander_advanced"]):
    adv1, adv2, adv3 = st.columns(3)
    with adv1:
        kerf = st.number_input(t["kerf_label"], min_value=0, max_value=10, value=4, step=1)
    with adv2:
        penalty = st.number_input(
            t["penalty_label"], min_value=0.0, max_value=20.0,
            value=1.5, step=0.5, help=t["penalty_help"],
        )
    with adv3:
        time_limit = st.number_input(
            t["time_label"], min_value=5, max_value=300, value=30, step=5,
        )

st.divider()

# ---------------------------------------------------------------------------
# 3. Optimize button
# ---------------------------------------------------------------------------
pieces_valid   = pieces_df_valid(st.session_state.pieces_df)
current_pieces = df_to_pieces(st.session_state.pieces_df)
max_piece      = max((l for l, _ in current_pieces), default=0)
pieces_fit     = max_piece <= max_stock

if not pieces_fit and current_pieces:
    st.warning(t["warning_too_long"].format(max_piece=max_piece, max_stock=int(max_stock)))

run_disabled = not pieces_valid or not pieces_fit

if st.button(t["btn_optimize"], type="primary", disabled=run_disabled):
    with st.spinner("⏳"):
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
                st.session_state.run_mode  = "auto"
            else:
                sol = optimize(
                    current_pieces,
                    max_stock_length=int(max_stock),
                    kerf=int(kerf),
                    max_distinct_lengths=int(mode),
                    time_limit_s=float(time_limit),
                )
                st.session_state.solutions = [sol]
                st.session_state.run_mode  = "fixed"
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
        st.info(t["info_configure"])
    else:
        st.info(t["info_add_pieces"])
else:
    solutions: list[Solution] = st.session_state.solutions
    run_mode   = st.session_state.get("run_mode", "fixed")
    solve_time = st.session_state.get("solve_time", 0)

    st.header(t["section_results"])
    st.caption(t["caption_solved"].format(time=solve_time))

    if run_mode == "auto" and len(solutions) > 1:
        recommended  = solutions[0]
        lengths_str  = ", ".join(f"{fmt(l)} mm" for l in recommended.stock_lengths)
        st.subheader(t["subheader_recommended"].format(
            lengths=lengths_str, util=recommended.utilization_pct
        ))
        show_detail_view(recommended, int(kerf), key_prefix="auto_rec")

        with st.expander(t["expander_compare"]):
            selected_idx = st.session_state.get("selected_k", 0)
            card_cols    = st.columns(len(solutions))

            for idx, (col, sol) in enumerate(zip(card_cols, solutions)):
                with col:
                    is_recommended = idx == 0
                    is_selected    = idx == selected_idx
                    tag = f" {t['tag_recommended']}" if is_recommended else ""
                    with st.container(border=True):
                        st.markdown(f"**k = {sol.distinct_count}{tag}**")
                        st.metric(t["metric_utilization"], f"{sol.utilization_pct:.1f}%")
                        st.metric(t["metric_distinct"],    sol.distinct_count)
                        st.metric(t["metric_bars"],        sum(sol.bar_counts))
                        st.metric(t["metric_waste"],       f"{fmt(sol.total_waste_mm)} mm")
                        lengths_str_c = ", ".join(f"{fmt(l)} mm" for l in sol.stock_lengths)
                        st.caption(t["caption_stock"].format(lengths=lengths_str_c))
                        if st.button(
                            t["btn_view_details"] if not is_selected else t["btn_showing_details"],
                            key=f"card_btn_{idx}",
                            disabled=is_selected,
                            use_container_width=True,
                        ):
                            st.session_state.selected_k = idx
                            st.rerun()

            if selected_idx != 0:
                st.divider()
                sel  = solutions[selected_idx]
                lstr = ", ".join(f"{fmt(l)} mm" for l in sel.stock_lengths)
                st.subheader(t["subheader_compare_detail"].format(
                    k=sel.distinct_count, lengths=lstr
                ))
                show_detail_view(sel, int(kerf), key_prefix=f"detail_{selected_idx}")

    else:
        sol         = solutions[0]
        lengths_str = ", ".join(f"{fmt(l)} mm" for l in sol.stock_lengths)
        st.subheader(t["subheader_detail"].format(
            k=sol.distinct_count, lengths=lengths_str, util=sol.utilization_pct
        ))
        show_detail_view(sol, int(kerf), key_prefix="single")

    st.divider()
    if st.button(t["btn_start_over"]):
        st.session_state.pieces_df = pd.DataFrame(
            columns=["Length (mm)", "Quantity"]
        ).astype({"Length (mm)": int, "Quantity": int})
        st.session_state.solutions = []
        st.session_state.selected_k = None
        st.rerun()
