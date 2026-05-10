"""UI string translations for English and German."""

from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Page
        "page_title":           "Profile Cutter — Cutting Stock Optimizer",
        "title":                "✂️ Profile Cutter — Cutting Stock Optimizer",
        "subtitle":             (
            "Enter the aluminum or metal facade profile pieces you need; "
            "the optimizer finds the stock length(s) to order that minimize "
            "material waste while keeping your SKU count low."
        ),
        # Pieces section
        "section_pieces":       "Required Pieces",
        "col_length":           "Length (mm)",
        "col_qty":              "Quantity",
        "btn_add":              "Add",
        "btn_load_example":     "Load example",
        "btn_load_advanced":    "Load advanced example",
        "btn_clear":            "Clear all",
        "caption_pieces":       "**{count}** pieces · **{mm}** mm total ({m:.2f} m)",
        # Settings
        "section_settings":     "Settings",
        "max_stock_label":      "Max stock length (mm)",
        "mode_label":           "Max distinct stock lengths",
        "mode_help":            "Auto runs k=1, 2, 3 and recommends the best trade-off.",
        "expander_advanced":    "Advanced",
        "kerf_label":           "Saw kerf (mm)",
        "penalty_label":        "Distinct-length penalty (%)",
        "penalty_help":         "Extra utilization required to justify one more distinct stock length.",
        "time_label":           "Solver time limit (s)",
        # Optimize
        "btn_optimize":         "Optimize",
        "warning_too_long":     (
            "Longest piece ({max_piece:,} mm) exceeds max stock length "
            "({max_stock:,} mm). Increase max stock length."
        ),
        # Results
        "section_results":      "Results",
        "caption_solved":       "Solved in {time:.1f} s",
        "subheader_recommended":"Recommended — Stock: {lengths} — Utilization: {util:.1f}%",
        "expander_compare":     "Compare k=1 / k=2 / k=3 options",
        "tag_recommended":      "⭐ Recommended",
        "metric_utilization":   "Utilization",
        "metric_distinct":      "Distinct SKUs",
        "metric_bars":          "Total bars",
        "metric_waste":         "Waste",
        "caption_stock":        "Stock: {lengths}",
        "btn_view_details":     "View details",
        "btn_showing_details":  "Showing details",
        "subheader_detail":     "k = {k}  —  Stock: {lengths}  —  Utilization: {util:.1f}%",
        "subheader_compare_detail": "Detailed view — k = {k} ({lengths})",
        # Detail view
        "subheader_order":      "Order Summary",
        "caption_order":        "You can increase the quantity for a buffer — totals update live.",
        "col_stock_length":     "Stock Length (mm)",
        "col_qty_order":        "Quantity to Order",
        "metric_total_ordered": "Total Ordered",
        "metric_total_used":    "Total Used",
        "metric_waste_val":     "{mm:,} mm ({pct:.1f}%)",
        "subheader_cutting":    "Cutting Plan",
        "btn_download":         "⬇ Download cutting plan as Excel",
        # Empty states
        "info_configure":       "Configure your pieces and settings, then click **Optimize**.",
        "info_add_pieces":      "Add pieces above to get started.",
        # Bottom
        "btn_start_over":       "Start over for another profile",
        # Excel
        "xl_sheet":             "Cutting Plan",
        "xl_input_title":       "Input Materials",
        "xl_input_length":      "Length (mm)",
        "xl_input_qty":         "Quantity",
        "xl_input_total":       "Total Length (mm)",
        "xl_input_total_row":   "Total",
        "xl_cutting_title":     "Cutting List",
        "xl_cut_bar":           "Bar",
        "xl_cut_stock":         "Stock Length (mm)",
        "xl_cut_pieces":        "Pieces (mm)",
        "xl_cut_count":         "Piece Count",
        "xl_cut_waste":         "Waste (mm)",
        "xl_cut_util":          "Utilization (%)",
        "xl_order_title":       "List of Order",
        "xl_order_qty":         "Qty to Order",
        "xl_order_stock":       "Stock Length (mm)",
        # Chart
        "chart_waste":          "Waste",
        "chart_kerf":           "Kerf",
    },

    "de": {
        # Page
        "page_title":           "Profile Cutter — Schnittoptimierung",
        "title":                "✂️ Profile Cutter — Schnittoptimierung",
        "subtitle":             (
            "Geben Sie die benötigten Aluminium- oder Metallfassadenprofile ein; "
            "der Optimierer ermittelt die zu bestellenden Stablänge(n), "
            "die den Materialverschnitt minimieren und die Anzahl der SKUs gering halten."
        ),
        # Pieces section
        "section_pieces":       "Benötigte Profile",
        "col_length":           "Länge (mm)",
        "col_qty":              "Anzahl",
        "btn_add":              "Hinzufügen",
        "btn_load_example":     "Beispiel laden",
        "btn_load_advanced":    "Erweitertes Beispiel laden",
        "btn_clear":            "Alles löschen",
        "caption_pieces":       "**{count}** Teile · **{mm}** mm gesamt ({m:.2f} m)",
        # Settings
        "section_settings":     "Einstellungen",
        "max_stock_label":      "Max. Stablänge (mm)",
        "mode_label":           "Max. verschiedene Stablängen",
        "mode_help":            "Auto führt k=1, 2, 3 aus und empfiehlt den besten Kompromiss.",
        "expander_advanced":    "Erweitert",
        "kerf_label":           "Schnittbreite (mm)",
        "penalty_label":        "Längenvarianten-Malus (%)",
        "penalty_help":         "Zusätzliche Auslastung, die eine weitere Stablänge rechtfertigen muss.",
        "time_label":           "Solver-Zeitlimit (s)",
        # Optimize
        "btn_optimize":         "Optimieren",
        "warning_too_long":     (
            "Längstes Teil ({max_piece:,} mm) überschreitet die max. Stablänge "
            "({max_stock:,} mm). Bitte max. Stablänge erhöhen."
        ),
        # Results
        "section_results":      "Ergebnisse",
        "caption_solved":       "Gelöst in {time:.1f} s",
        "subheader_recommended":"Empfohlen — Stab: {lengths} — Auslastung: {util:.1f}%",
        "expander_compare":     "k=1 / k=2 / k=3 Optionen vergleichen",
        "tag_recommended":      "⭐ Empfohlen",
        "metric_utilization":   "Auslastung",
        "metric_distinct":      "Verschiedene Stablängen",
        "metric_bars":          "Stäbe gesamt",
        "metric_waste":         "Verschnitt",
        "caption_stock":        "Stab: {lengths}",
        "btn_view_details":     "Details anzeigen",
        "btn_showing_details":  "Details aktiv",
        "subheader_detail":     "k = {k}  —  Stab: {lengths}  —  Auslastung: {util:.1f}%",
        "subheader_compare_detail": "Detailansicht — k = {k} ({lengths})",
        # Detail view
        "subheader_order":      "Bestellübersicht",
        "caption_order":        "Menge für Puffer erhöhen — Gesamtwerte werden live aktualisiert.",
        "col_stock_length":     "Stablänge (mm)",
        "col_qty_order":        "Bestellmenge",
        "metric_total_ordered": "Gesamt bestellt",
        "metric_total_used":    "Gesamt verwendet",
        "metric_waste_val":     "{mm:,} mm ({pct:.1f}%)",
        "subheader_cutting":    "Schnittplan",
        "btn_download":         "⬇ Schnittplan als Excel herunterladen",
        # Empty states
        "info_configure":       "Profile und Einstellungen konfigurieren, dann **Optimieren** klicken.",
        "info_add_pieces":      "Oben Profile hinzufügen, um zu beginnen.",
        # Bottom
        "btn_start_over":       "Neustart für ein anderes Profil",
        # Excel
        "xl_sheet":             "Schnittplan",
        "xl_input_title":       "Eingabematerial",
        "xl_input_length":      "Länge (mm)",
        "xl_input_qty":         "Anzahl",
        "xl_input_total":       "Gesamtlänge (mm)",
        "xl_input_total_row":   "Gesamt",
        "xl_cutting_title":     "Schnittliste",
        "xl_cut_bar":           "Stab",
        "xl_cut_stock":         "Stablänge (mm)",
        "xl_cut_pieces":        "Teile (mm)",
        "xl_cut_count":         "Teilanzahl",
        "xl_cut_waste":         "Verschnitt (mm)",
        "xl_cut_util":          "Auslastung (%)",
        "xl_order_title":       "Bestellliste",
        "xl_order_qty":         "Bestellmenge",
        "xl_order_stock":       "Stablänge (mm)",
        # Chart
        "chart_waste":          "Verschnitt",
        "chart_kerf":           "Schnitt",
    },
}


def T(lang: str) -> dict[str, str]:
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"])
