"""Render a markdown summary and plots from a bench results JSON file.

Usage: python bench/report.py bench/results/<stamp>_<env>.json
Every number written here is read from the results file.
"""
import json
import sys
from pathlib import Path

METHODS = ["tfidf", "vector_exact", "vector_hnsw", "hybrid"]
HEADLINE = ["precision@3", "precision@10"]
SECONDARY = ["mrr@10", "ndcg@10", "hit_rate@3", "hit_rate@10", "recall@10", "max_recall@10"]

# Validated categorical palette (light surface #fcfcfb), fixed slot order
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]


def f(x, nd=3):
    return "" if x is None else f"{x:.{nd}f}"


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def md_environment(env):
    s = env["server_settings"]
    rows = [
        ("Environment", env["env"] + (" (DRY RUN)" if env["dry_run"] else "")),
        ("Timestamp (UTC)", env["timestamp_utc"]),
        ("Host", env.get("host_description") or ""),
        ("Azure SKU", env.get("azure_sku") or ""),
        ("Postgres", env["postgres_version"]),
        ("pgvector", env["pgvector_version"]),
        ("SSL in use", env["db_ssl"]),
        ("Client CPU", env["client"].get("host_cpu") or env["client"].get("cpu_model_container") or ""),
        ("Client CPUs visible", env["client"]["cpu_count_visible"]),
        ("Docker resources", env["client"].get("docker_resources") or ""),
        ("shared_buffers / work_mem / maintenance_work_mem",
         f"{s['shared_buffers']} / {s['work_mem']} / {s['maintenance_work_mem']}"),
        ("max_parallel_maintenance_workers", s["max_parallel_maintenance_workers"]),
        ("Reference rows / eval rows", f"{env['corpus']['reference_rows']} / {env['corpus']['eval_rows']}"),
        ("Embedding model", f"{env['embedding_model']} @ {env['embedding_model_revision']}"),
        ("Seed", env["seed"]),
        ("Git commit", f"{env['git']['commit']} (dirty files: {env['git']['dirty_files']})"),
    ]
    return table(["Field", "Value"], rows)


def md_part_a(a):
    out = []
    for name, title in (("clause", "Clause-as-query"), ("question", "CUAD category questions")):
        qs = a["query_sets"][name]
        out.append(f"### {title} ({qs['n_queries']} queries, {qs['n_distinct_texts']} distinct texts)\n")
        rows = []
        for m in METHODS:
            mm = qs["methods"][m]
            mean, ci = mm["mean"], mm["ci95"]
            rows.append([m] + [f"{f(mean[k])} [{f(ci[k][0])}, {f(ci[k][1])}]" for k in HEADLINE]
                        + [f(mean[k]) for k in SECONDARY])
        out.append(table(["Method", "P@3 [95% CI]", "P@10 [95% CI]"] + SECONDARY, rows))
        out.append(f"\nHybrid HNSW leg: minimum candidates returned = {qs['hybrid_hnsw_candidates_min']}.")
        if qs["categories_without_queries"]:
            out.append(f"Categories without queries in this set: {', '.join(qs['categories_without_queries'])}.")
        out.append("\nWeakest 5 categories by P@10:\n")
        out.append(table(["Method", "Categories (P@10, n queries)"], [
            [m, "; ".join(f"{w['category']} ({f(w['precision@10'])}, n={w['n_queries']})"
                          for w in qs["methods"][m]["weakest_5_by_precision@10"])]
            for m in METHODS
        ]))
        if name == "clause":
            cats = list(qs["methods"]["tfidf"]["per_category"])
            out.append("\nPer-category P@10 (clause-as-query):\n")
            out.append(table(["Category", "n"] + METHODS, [
                [c, qs["methods"]["tfidf"]["per_category"][c]["n_queries"]]
                + [f(qs["methods"][m]["per_category"][c]["precision@10"]) for m in METHODS]
                for c in cats
            ]))
        out.append("")
    p = a["plans"]
    out.append(f"EXPLAIN check: vector_exact nodes {p['vector_exact']['nodes']} (HNSW used: "
               f"{p['vector_exact']['uses_hnsw']}); vector_hnsw nodes {p['vector_hnsw']['nodes']} "
               f"(HNSW used: {p['vector_hnsw']['uses_hnsw']}).")
    return "\n".join(out)


def md_part_b(b):
    out = [table(["Index", "Build (s)", "Size (bytes)", "DDL"], [
        [i["name"], f(i["build_seconds"], 2), i["size_bytes"], f"`{i['ddl']}`"] for i in b["indexes"]
    ]), ""]
    rows = []
    for c in b["configs"]:
        label = c["label"] + (" (scans all lists)" if c.get("scans_all_lists") else "")
        s = c["server"]["execution_ms"]
        rows.append([label, f(c["recall@10_vs_exact"], 4), f(c["client_ms"]["p50"], 2), f(c["client_ms"]["p95"], 2),
                     f(c["client_ms"]["p99"], 2), f(c["qps"], 1), f(s["p50"], 3), f(s["p95"], 3), f(s["p99"], 3),
                     "yes" if c["plan_check_passed"] else "NO",
                     "yes" if c["planner_default_uses_expected_index"] else
                     "no (" + ", ".join(c["planner_default_plan"]["nodes"]) + ")"])
    out.append(f"{b['n_queries']} timed queries per configuration (after warmup).\n")
    out.append(table(["Config", "Recall@10 vs exact", "Client p50 ms", "p95", "p99", "QPS",
                      "Server exec p50 ms", "p95", "p99", "Plan check", "Planner picks it unforced"], rows))
    out.append("\nIndexed configs are measured with enable_seqscan=off so the index is exercised; the last "
               "column shows whether the planner would use the index without that.")
    out.append(f"\nIndexes restored to start state: {b['indexes_restored']}.")
    return "\n".join(out)


def md_filtered(fb):
    out = [f"Iterative scan supported: {fb['iterative_scan_supported']}"
           + (f" ({fb['iterative_scan_unsupported_reason']})" if fb["iterative_scan_unsupported_reason"] else "")
           + f". {fb['n_queries_per_category']} queries per category.\n"]
    modes = list(next(iter(fb["categories"].values()))["modes"])
    rows = []
    for cat, e in fb["categories"].items():
        cells = []
        for m in modes:
            mm = e["modes"][m]
            idx = ",".join(mm["plan"]["indexes"]) or "none"
            cells.append(f"{f(mm['recall@10_vs_exact_filtered'])} / {f(mm['mean_result_count'], 1)} ({idx})")
        rows.append([e["group"], cat, e["reference_rows"]] + cells)
    out.append("Cells: recall@10 vs exact filtered / mean result count (indexes in plan).\n")
    out.append(table(["Group", "Category", "Ref rows"] + modes, rows))
    return "\n".join(out)


def md_part_c(c):
    info = c["info"]
    out = [f"{c['runs']} timed runs after {c['warmup_runs']} warmup. Clauses: {info['num_clauses']}, "
           f"priority: {info['num_priority']}, classifier: {info['classifier']}, retriever: {info['retriever']}, "
           f"related: {info['num_related']}, precedents: {info['num_precedents']}. {c['note']}.\n"]
    out.append(table(["Stage", "Median ms", "p95 ms"],
                     [[k, f(v["median"], 2), f(v["p95"], 2)] for k, v in c["stages_ms"].items()]
                     + [["total (median of per-run sums)", f(c["total_median_ms"], 2), ""]]))
    return "\n".join(out)


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def plot_tradeoff(b, path):
    import matplotlib
    import matplotlib.ticker
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    groups = {"HNSW (ef_search)": [], "IVFFlat lists=small": [], "IVFFlat lists=sqrt(N)": [], "Exact": []}
    ivf_lists = sorted({c["lists"] for c in b["configs"] if "lists" in c})
    for c in b["configs"]:
        if c["label"].startswith("hnsw"):
            groups["HNSW (ef_search)"].append(c)
        elif c["label"] == "exact":
            groups["Exact"].append(c)
        elif c.get("lists") == ivf_lists[0]:
            groups["IVFFlat lists=small"].append(c)
        else:
            groups["IVFFlat lists=sqrt(N)"].append(c)
    names = {"IVFFlat lists=small": f"IVFFlat lists={ivf_lists[0]}",
             "IVFFlat lists=sqrt(N)": f"IVFFlat lists={ivf_lists[-1]}"}

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), facecolor=SURFACE, sharey=True)
    for ax, key, title in ((axes[0], "client", "Client round trip p50 (ms)"),
                           (axes[1], "server", "Server execution p50 (ms)")):
        style_axes(ax)
        for color, (g, cs) in zip(SERIES, groups.items()):
            if not cs:
                continue
            xs = [c["client_ms"]["p50"] if key == "client" else c["server"]["execution_ms"]["p50"] for c in cs]
            ys = [c["recall@10_vs_exact"] for c in cs]
            ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=7,
                    markeredgecolor=SURFACE, markeredgewidth=2, label=names.get(g, g))
            if g == "HNSW (ef_search)":
                for c, x, y in zip(cs, xs, ys):
                    ax.annotate(c["settings"]["hnsw__ef_search"], (x, y), textcoords="offset points",
                                xytext=(-8, 6), ha="right", fontsize=8, color=TEXT)
        ax.set_xscale("log")
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_xlabel(title + ", log scale", color=TEXT_2, fontsize=10)
    axes[0].set_ylabel("Recall@10 vs exact kNN", color=TEXT_2, fontsize=10)
    axes[0].legend(frameon=False, fontsize=9, labelcolor=TEXT)
    fig.suptitle("ANN recall vs latency (HNSW labels = ef_search)", color=TEXT, fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_methods(a, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), facecolor=SURFACE, sharey=True)
    width = 0.19
    for ax, (name, title) in zip(axes, (("clause", "Clause-as-query"), ("question", "Category questions"))):
        style_axes(ax)
        ax.grid(True, axis="y", color=GRID, linewidth=0.8)
        ax.grid(False, axis="x")
        qs = a["query_sets"][name]
        x = np.arange(len(HEADLINE))
        for i, (m, color) in enumerate(zip(METHODS, SERIES)):
            mm = qs["methods"][m]
            vals = [mm["mean"][k] for k in HEADLINE]
            lo = [mm["mean"][k] - mm["ci95"][k][0] for k in HEADLINE]
            hi = [mm["ci95"][k][1] - mm["mean"][k] for k in HEADLINE]
            pos = x + (i - 1.5) * (width + 0.01)
            ax.bar(pos, vals, width, color=color, label=m, edgecolor=SURFACE, linewidth=2)
            ax.errorbar(pos, vals, yerr=[lo, hi], fmt="none", ecolor=TEXT_2, elinewidth=1, capsize=2)
            for p, v, h in zip(pos, vals, hi):
                ax.text(p, v + h + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=8, color=TEXT)
        ax.set_xticks(x, ["Precision@3", "Precision@10"], color=TEXT)
        ax.set_title(f"{title} (n={qs['n_queries']})", color=TEXT, fontsize=10, loc="left")
    axes[0].set_ylabel("Mean precision (95% bootstrap CI)", color=TEXT_2, fontsize=10)
    axes[0].set_ylim(0, 1.05)
    axes[0].legend(frameon=False, fontsize=9, labelcolor=TEXT, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def render(results_path: Path):
    results_path = Path(results_path)
    r = json.loads(results_path.read_text())
    stem = results_path.with_suffix("")
    env = r["environment"]
    parts = []
    if env["dry_run"]:
        parts.append("> **DRY RUN: exercises the harness on small subsets. Not for reporting.**\n")
    parts += [f"# Retrieval benchmark: {env['env']}\n", f"Source: `{results_path.name}`. "
              f"Design: `{r['preregistration']}`. Corpus stats: `{r['corpus_meta']}`.\n",
              "## Environment\n", md_environment(env), ""]
    if "part_a" in r:
        parts += ["## A. Retrieval quality (eval split -> reference split)\n", md_part_a(r["part_a"]), ""]
        plot_methods(r["part_a"], f"{stem}_methods.png")
        parts.append(f"![Method comparison]({stem.name}_methods.png)\n")
    if "part_b" in r:
        parts += ["## B. ANN index tradeoffs\n", md_part_b(r["part_b"]), ""]
        plot_tradeoff(r["part_b"], f"{stem}_ann_tradeoff.png")
        parts.append(f"![Recall vs latency]({stem.name}_ann_tradeoff.png)\n")
    if "part_b_filtered" in r:
        parts += ["## B. Filtered vector search\n", md_filtered(r["part_b_filtered"]), ""]
    if "part_c" in r:
        parts += ["## C. End-to-end (sample_contract.pdf)\n", md_part_c(r["part_c"]), ""]
    out = Path(f"{stem}.md")
    out.write_text("\n".join(parts) + "\n")
    print(f"Wrote {out}")
    return out


if __name__ == "__main__":
    render(Path(sys.argv[1]))
