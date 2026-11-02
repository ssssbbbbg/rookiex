#!/usr/bin/env python3
"""
ghbuild.py —— 触发 / 轮询 / 下载 GitHub Actions 构建，并把一切日志落到本地。

全程只用 GITHUBTOKEN 环境变量，不写入文件、不打印。

用法:
    python3 ghbuild.py                 # 触发构建 + 等完 + 拉日志
    python3 ghbuild.py --status        # 只看最近一次
    python3 ghbuild.py --logs 123456   # 拉指定 run 的日志
    python3 ghbuild.py --dir out       # 日志输出目录（默认 ./buildlogs）

产物:
    <dir>/run_<id>/meta.json       run 元信息
    <dir>/run_<id>/run.log         整个 run 的全部步骤日志
    <dir>/run_<id>/failed.log      失败步骤的孤立日志（如果有）
    <dir>/history.jsonl            每次调用的历史一行
    <dir>/latest -> run_<最新id>   软链
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
import io
import zipfile
from datetime import datetime, timezone

API = "https://api.github.com"
REPO = os.environ.get("GH_REPO", "ssssbbbbg/rookiex")
WORKFLOW = os.environ.get("GH_WORKFLOW", "build.yml")
BRANCH = os.environ.get("GH_BRANCH", "main")

TOKEN = os.environ.get("GITHUBTOKEN") or os.environ.get("GH_TOKEN") or ""
if not TOKEN:
    print("[x] 没找到 GITHUBTOKEN 环境变量")
    sys.exit(2)


def req(path, method="GET", data=None, accept="application/vnd.github+json", raw=False):
    url = path if path.startswith("http") else API + path
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, method=method)
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Accept", accept)
    r.add_header("X-GitHub-Api-Version", "2022-11-28")
    if body:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            blob = resp.read()
            if raw:
                return blob
            return json.loads(blob) if blob else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        print(f"[!] HTTP {e.code} {path}\n    {detail[:500]}")
        return {"__error__": e.code, "detail": detail}


def now():
    return datetime.now(timezone.utc)


def logfile(d: str, name: str, text: str):
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def history(d: str, rec: dict):
    os.makedirs(d, exist_ok=True)
    rec["at"] = now().isoformat()
    with open(os.path.join(d, "history.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def latest_run():
    for branch in (BRANCH, "master"):
        r = req(f"/repos/{REPO}/actions/workflows/{WORKFLOW}/runs?per_page=5&branch={branch}")
        if "__error__" in r:
            continue
        runs = r.get("workflow_runs") or []
        if runs:
            return runs[0]
    r = req(f"/repos/{REPO}/actions/workflows/{WORKFLOW}/runs?per_page=5")
    runs = r.get("workflow_runs") or []
    return runs[0] if runs else None


def trigger():
    ok = False
    for branch in (BRANCH, "master"):
        r = req(f"/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
                method="POST", data={"ref": branch})
        if "__error__" not in r:
            print(f"[+] 已触发构建 ref={branch}")
            ok = True
            break
    if not ok:
        print("[!] 触发失败，检查 workflow 是否有 workflow_dispatch")
    return ok


def wait_run(started_before, timeout_min=25):
    t0 = time.time()
    seen = None
    while time.time() - t0 < timeout_min * 60:
        r = latest_run()
        if r:
            seen = r
            st = r.get("status")
            cc = r.get("conclusion")
            print(f"    run {r['id']} status={st} conclusion={cc}")
            if st == "completed":
                return r
        time.sleep(15)
    return seen


def fetch_logs(run_id, outdir):
    d = os.path.join(outdir, f"run_{run_id}")
    blob = req(f"/repos/{REPO}/actions/runs/{run_id}/logs", raw=True)
    if isinstance(blob, dict):
        logfile(d, "run.log", "拉取日志失败: " + json.dumps(blob, ensure_ascii=False))
        return d
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
        parts = []
        for n in sorted(zf.namelist()):
            parts.append("=" * 70)
            parts.append("# " + n)
            parts.append("=" * 70)
            parts.append(zf.read(n).decode("utf-8", "ignore"))
        logfile(d, "run.log", "\n".join(parts))
        # 单挑失败步骤
        fail = [x for x in zf.namelist() if "_failed" in x or "failure" in x.lower()]
        if fail:
            logfile(d, "failed.log", "\n".join(
                zf.read(n).decode("utf-8", "ignore") for n in fail))
    except zipfile.BadZipFile:
        logfile(d, "run.log", blob.decode("utf-8", "ignore"))
    return d


def save_meta(run, outdir):
    d = os.path.join(outdir, f"run_{run['id']}")
    os.makedirs(d, exist_ok=True)
    meta = {
        "id": run.get("id"),
        "name": run.get("name"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "branch": run.get("head_branch"),
        "sha": run.get("head_sha"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "url": run.get("html_url"),
        "artifacts_url": run.get("artifacts_url"),
    }
    logfile(d, "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    return meta, d


def pull_artifacts(run_id, d):
    r = req(f"/repos/{REPO}/actions/runs/{run_id}/artifacts")
    arts = r.get("artifacts") or []
    if not arts:
        print("    （无 artifact）")
        return
    adir = os.path.join(d, "artifacts")
    os.makedirs(adir, exist_ok=True)
    for a in arts:
        print(f"    artifact: {a['name']} ({a['size_in_bytes']} B)")
        blob = req(a["archive_download_url"], raw=True)
        if isinstance(blob, dict):
            continue
        p = os.path.join(adir, a["name"] + ".zip")
        with open(p, "wb") as f:
            f.write(blob)


def main():
    args = sys.argv[1:]
    outdir = "./buildlogs"
    if "--dir" in args:
        outdir = args[args.index("--dir") + 1]
    os.makedirs(outdir, exist_ok=True)

    if "--logs" in args:
        rid = int(args[args.index("--logs") + 1])
        r = req(f"/repos/{REPO}/actions/runs/{rid}")
        meta, d = save_meta(r, outdir)
        fetch_logs(rid, outdir)
        report(meta, d, outdir)
        return

    if "--status" in args:
        r = latest_run()
        if not r:
            print("没有构建记录")
            return
        meta, d = save_meta(r, outdir)
        if r.get("status") == "completed":
            fetch_logs(r["id"], outdir)
        report(meta, d, outdir)
        return

    before = now()
    if not trigger():
        print("[x] 无法触发，用 --status 查看已有 run")
        return
    print("[.] 等待 run 出现…")
    run = wait_run(before)
    if not run:
        print("[x] 超时未见 run")
        return
    meta, d = save_meta(run, outdir)
    fetch_logs(run["id"], outdir)
    if run.get("conclusion") == "success":
        pull_artifacts(run["id"], d)
    report(meta, d, outdir)


def report(meta, d, outdir):
    latest = os.path.join(outdir, "latest")
    try:
        if os.path.islink(latest) or os.path.exists(latest):
            os.unlink(latest)
        os.symlink(os.path.basename(d), latest)
    except OSError:
        pass
    history(outdir, meta)
    ok = meta.get("conclusion") == "success"
    print()
    print("=" * 50)
    print(f"结论: {meta.get('conclusion')}")
    print(f"run : {meta.get('url')}")
    print(f"日志: {d}/run.log")
    for f in os.listdir(d):
        p = os.path.join(d, f)
        if os.path.isdir(p):
            print(f"  {f}/ {os.listdir(p)}")
    print("=" * 50)
    if not ok:
        fp = os.path.join(d, "run.log")
        if os.path.exists(fp):
            txt = open(fp, encoding="utf-8", errors="ignore").read()
            marks = ("error:", "FAILURE:", "What went wrong", "Caused by:")
            for line in txt.splitlines():
                if any(m in line for m in marks):
                    print("  > " + line.strip()[:200])


if __name__ == "__main__":
    main()
