"""Cost per full audit by triage mode, from results/eval.json only (no invented numbers).

Every cost uses the per-unit costs measured in the evaluation run (eval.json, cost.extrapolation):
  cost = text_pages x text_page_usd + vision_pages x vision_page_usd
         + candidates x triage_usd_per_candidate + candidates x pass_rate x verdict_usd
Safe and fast triage differ in triage cost per candidate and pass rate; "no triage" sends every
candidate to Ultra. "Ultra reads every page" also has Ultra do the claim extraction, priced from
the measured extraction token counts x Ultra's prices (llm.PRICES).

Recall (from the same evaluation): of the candidate pairs Ultra graded RED or ORANGE, how many
the triage mode would have kept (known-issue pages + planted test). With no triage every
candidate reaches Ultra, so that is the reference. Ultra-extraction recall was not measured.
"""

import re

from tigerfish import llm


def _stage(rows, start):
    r = next(r for r in rows if r["stage"].startswith(start))
    pages = int(re.search(r"\((\d+)\)", r["stage"]).group(1))
    return r, pages


def tokens_per_page(e):
    """Measured claim-extraction tokens per page: {"text": (in, out), "vision": (in, out)}."""
    rows = e["cost"]["rows"]
    out = {}
    for kind, start in (("text", "Claim extraction, text pages"), ("vision", "Claim extraction, vision pages")):
        r, pages = _stage(rows, start)
        out[kind] = (r["in_tokens"] / pages, r["out_tokens"] / pages)
    return out


def recall(e):
    """{"safe": (kept, flagged), "fast": (kept, flagged)} over known-issue and planted pages."""
    flagged = safe_missed = fast_missed = 0
    for tv in (e["known"].get("triage_validation"), e["planted"].get("triage_validation")):
        if not tv:
            continue
        flagged += sum(1 for r in tv["rows"] if r.get("ultra_grade") in ("RED", "ORANGE"))
        safe_missed += len(tv["violations"])
        fast_missed += tv["fast_violations"]
    return {"safe": (flagged - safe_missed, flagged), "fast": (flagged - fast_missed, flagged),
            "none": (flagged, flagged)}


def modes(e):
    """Rows for the chart: {mode, usd, verdicts, recall: (kept, of) or None, recall_note, formula}."""
    x = e["cost"]["extrapolation"]
    u = x["per_unit"]
    text, vision, cand = x["pages_text"], x["pages_vision"], x["candidates"]
    extract = text * u["text_page_usd"] + vision * u["vision_page_usd"]
    rc = recall(e)

    def triaged(triage_usd, pass_rate):
        return extract + cand * triage_usd + cand * pass_rate * u["verdict_usd"]

    price_in, price_out = llm.PRICES[llm.ULTRA]
    tpp = tokens_per_page(e)
    ultra_page = {k: (i * price_in + o * price_out) / 1e6 for k, (i, o) in tpp.items()}
    ultra_extract = text * ultra_page["text"] + vision * ultra_page["vision"]

    ex = (f"{text} text pages x ${u['text_page_usd']} + {vision} scanned pages x "
          f"${u['vision_page_usd']}")
    return [
        {"mode": "Safe triage (default)", "usd": triaged(u["triage_usd_per_candidate"], u["triage_pass_rate"]),
         "verdicts": round(cand * u["triage_pass_rate"]), "recall": rc["safe"],
         "recall_note": "Ultra-flagged pairs kept by triage",
         "formula": f"{ex} + {cand:,} candidates x ${u['triage_usd_per_candidate']} triage + "
                    f"{cand:,} x {u['triage_pass_rate']:.2f} pass rate x ${u['verdict_usd']} Ultra verdict"},
        {"mode": "Fast triage (quotes only)",
         "usd": triaged(u["triage_usd_per_candidate_fast"], u["triage_pass_rate_fast"]),
         "verdicts": round(cand * u["triage_pass_rate_fast"]), "recall": rc["fast"],
         "recall_note": "Ultra-flagged pairs kept by triage",
         "formula": f"{ex} + {cand:,} candidates x ${u['triage_usd_per_candidate_fast']} triage + "
                    f"{cand:,} x {u['triage_pass_rate_fast']:.2f} pass rate x ${u['verdict_usd']} Ultra verdict"},
        {"mode": "No triage", "usd": extract + cand * u["verdict_usd"], "verdicts": cand,
         "recall": rc["none"], "recall_note": "reference: every candidate reaches Ultra",
         "formula": f"{ex} + {cand:,} candidates x ${u['verdict_usd']} Ultra verdict"},
        {"mode": "Ultra reads every page (estimate)", "usd": ultra_extract + cand * u["verdict_usd"],
         "verdicts": cand, "recall": None, "recall_note": "not measured",
         "formula": (f"{text} text pages x ({tpp['text'][0]:,.0f} in x ${price_in} + "
                     f"{tpp['text'][1]:,.0f} out x ${price_out}) / 1M + {vision} scanned pages x "
                     f"({tpp['vision'][0]:,.0f} in x ${price_in} + {tpp['vision'][1]:,.0f} out x "
                     f"${price_out}) / 1M + {cand:,} candidates x ${u['verdict_usd']} Ultra verdict")},
    ]


ACCENT = "#0F5E5E"
ESTIMATE = "#8FB3B3"
TEXT = "#1C2B33"


def figure(rows):
    import plotly.graph_objects as go
    labels = [r["mode"] for r in rows][::-1]
    usd = [r["usd"] for r in rows][::-1]
    recall_txt = [(f"recall {r['recall'][0]} of {r['recall'][1]}" if r["recall"] else "recall not measured")
                  for r in rows][::-1]
    fig = go.Figure(go.Bar(
        x=usd, y=labels, orientation="h",
        marker={"color": [ESTIMATE if r["recall"] is None else ACCENT for r in rows][::-1],
                "cornerradius": 4},
        text=[f"${v:.2f} · {t}" for v, t in zip(usd, recall_txt)], textposition="outside",
        textfont={"color": TEXT, "size": 13}, cliponaxis=False,
        customdata=[[r["verdicts"], r["recall_note"]] for r in rows][::-1],
        hovertemplate="<b>%{y}</b><br>$%{x:.2f} per full audit<br>%{customdata[0]:,} Ultra verdicts"
                      "<br>Recall: %{customdata[1]}<extra></extra>"))
    fig.update_layout(height=260, margin={"l": 0, "r": 150, "t": 10, "b": 30}, bargap=0.35,
                      paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", showlegend=False,
                      font={"color": TEXT, "family": "Inter, Segoe UI, sans-serif"},
                      xaxis={"title": "USD per full 1,213-page audit", "gridcolor": "#EEF1F2",
                             "zeroline": False, "tickprefix": "$"},
                      yaxis={"automargin": True})
    return fig


def render(e):
    import streamlit as st
    rows = modes(e)
    st.markdown("#### Cost per full audit, by triage mode")
    st.plotly_chart(figure(rows), width="stretch", config={"displayModeBar": False})
    st.markdown("| Mode | Cost | Ultra verdicts | Recall |\n|---|---:|---:|---|\n" + "\n".join(
        f"| {r['mode']} | ${r['usd']:.2f} | {r['verdicts']:,} | "
        + (f"{r['recall'][0]} of {r['recall'][1]} ({r['recall_note']})" if r["recall"] else r["recall_note"])
        + " |" for r in rows))
    with st.expander("How each number is computed"):
        for r in rows:
            st.markdown(f"**{r['mode']}**: `{r['formula']}`")
    st.caption("All unit costs and token counts are measured in the evaluation run "
               f"(results/eval.json, {e['generated']}); the full-audit totals are extrapolations "
               "from them. Recall counts candidate pairs on the known-issue pages and the planted "
               "test that Ultra graded RED or ORANGE, and how many each triage mode would have "
               "passed on to Ultra. The Ultra-every-page bar assumes Ultra would need the same "
               "tokens per page as the measured extraction models; its recall was not measured.")
