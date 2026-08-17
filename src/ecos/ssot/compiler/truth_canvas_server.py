"""Dual-Plane Truth Canvas Lightweight Web Server (ADR-0194).

Provides zero-dependency local Web UI for:
1. Visualizing domain facts across Weijian & Transfer projects
2. 14-Day Freshness SLA Countdown Badges (E-DOC-004)
3. Safe Form Generation & Writeback into _entities/facts/*.yaml
"""

from __future__ import annotations

import http.server
import json
import os
import urllib.parse
from pathlib import Path
from typing import Any

import yaml

from ecos.ssot.compiler.fact_inspector import FactInspector

CANVAS_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dual-Plane Truth Canvas | 事实态势大盘</title>
<style>
:root {
  --bg: #0d1117;
  --surface: #161b22;
  --border: #30363d;
  --text: #c9d1d9;
  --text-bright: #f0f6fc;
  --accent: #58a6ff;
  --green: #2ea043;
  --yellow: #d29922;
  --red: #f85149;
  --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
  line-height: 1.5;
  padding: 24px;
}
.container { max-width: 1200px; margin: 0 auto; }
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
  margin-bottom: 24px;
}
h1 { font-size: 20px; font-weight: 600; color: var(--text-bright); display: flex; align-items: center; gap: 8px; }
.badge-plane { background: #1f6feb22; color: var(--accent); border: 1px solid #1f6feb; padding: 2px 8px; border-radius: 12px; font-size: 12px; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
.stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.stat-label { font-size: 12px; color: #8b949e; text-transform: uppercase; }
.stat-value { font-size: 24px; font-weight: 700; color: var(--text-bright); margin-top: 4px; font-family: var(--font-mono); }
.facts-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; margin-bottom: 32px; }
.fact-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.fact-header { display: flex; justify-content: space-between; align-items: flex-start; }
.fact-id { font-family: var(--font-mono); font-size: 13px; font-weight: 600; color: var(--accent); }
.fact-name { font-size: 15px; font-weight: 600; color: var(--text-bright); margin-top: 4px; }
.fact-meta { font-size: 12px; color: #8b949e; display: flex; flex-wrap: wrap; gap: 12px; margin-top: 4px; }
.fact-body { background: #0d111788; border-radius: 6px; padding: 10px; font-family: var(--font-mono); font-size: 12px; white-space: pre-wrap; overflow-x: auto; max-height: 180px; }
.tag-fresh { background: #2ea04322; color: #3fb950; border: 1px solid #2ea043; padding: 2px 6px; border-radius: 4px; font-size: 11px; }
.tag-stale { background: #d2992222; color: #e3b341; border: 1px solid #d29922; padding: 2px 6px; border-radius: 4px; font-size: 11px; }
.tag-stage { background: #388bfd22; color: #58a6ff; border: 1px solid #388bfd44; padding: 2px 6px; border-radius: 4px; font-size: 11px; }
.form-section { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }
.form-title { font-size: 16px; font-weight: 600; color: var(--text-bright); margin-bottom: 16px; }
.form-group { margin-bottom: 14px; }
label { display: block; font-size: 12px; color: #8b949e; margin-bottom: 4px; }
input, select, textarea { width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text-bright); padding: 8px 12px; border-radius: 6px; font-family: inherit; font-size: 13px; }
input:focus, select:focus, textarea:focus { outline: none; border-color: var(--accent); }
button { background: #238636; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; }
button:hover { background: #2ea043; }
#toast { position: fixed; bottom: 20px; right: 20px; padding: 12px 20px; border-radius: 6px; font-size: 13px; display: none; }
.toast-success { background: #2ea043; color: white; }
.toast-error { background: #f85149; color: white; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>🛡️ Dual-Plane Truth Canvas <span class="badge-plane">Documents/Facts SSOT</span></h1>
    <div style="font-size: 13px; color: #8b949e;">ADR-0194 Clean Architecture</div>
  </header>

  <div class="stats-grid" id="statsGrid">
    <div class="stat-card"><div class="stat-label">事实实体总数</div><div class="stat-value" id="statTotal">-</div></div>
    <div class="stat-card"><div class="stat-label">14天保鲜率</div><div class="stat-value" id="statFreshRate">-</div></div>
    <div class="stat-card"><div class="stat-label">卫健委领域项目</div><div class="stat-value" id="statWeijian">-</div></div>
    <div class="stat-card"><div class="stat-label">国转中心转化实体</div><div class="stat-value" id="statTransfer">-</div></div>
  </div>

  <h2 style="font-size: 16px; color: var(--text-bright); margin-bottom: 12px;">📑 领域事实真源卡片流</h2>
  <div class="facts-grid" id="factsContainer">
    <div style="color: #8b949e; font-size: 13px;">加载事实数据中...</div>
  </div>

  <div class="form-section">
    <div class="form-title">➕ 录入新领域事实 (Safe Form Writeback)</div>
    <form id="factForm">
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
        <div class="form-group">
          <label>实体 ID (e.g. FACT-WJ-2026-002 / FACT-TF-2026-010)</label>
          <input type="text" id="entity_id" required placeholder="FACT-WJ-2026-002">
        </div>
        <div class="form-group">
          <label>业务领域 (Domain)</label>
          <select id="domain" required>
            <option value="work-weijian">work-weijian (卫健委信息化)</option>
            <option value="work-transfer">work-transfer (国转中心科技转化)</option>
          </select>
        </div>
      </div>
      <div style="display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 14px;">
        <div class="form-group">
          <label>实体名称 / 项目名称</label>
          <input type="text" id="name" required placeholder="电子健康卡全生命周期协同平台">
        </div>
        <div class="form-group">
          <label>负责处室 / 责任人</label>
          <input type="text" id="owner" required placeholder="规划信息处">
        </div>
        <div class="form-group">
          <label>生命周期阶段</label>
          <select id="lifecycle_stage">
            <option value="INITIATION">立项 (INITIATION)</option>
            <option value="PLANNING">规划 (PLANNING)</option>
            <option value="IMPLEMENTATION" selected>实施 (IMPLEMENTATION)</option>
            <option value="PILOT">试运行 (PILOT)</option>
            <option value="OPERATIONAL">运行 (OPERATIONAL)</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label>结构化事实 JSON / YAML (Key-Value 键值对)</label>
        <textarea id="facts_json" rows="4" placeholder='{"budget_million_cny": 5.2, "trl_level": 7, "dengbao_level": 3}'></textarea>
      </div>
      <button type="submit">安全校验并写入真源库</button>
    </form>
  </div>
</div>
<div id="toast"></div>

<script>
async function loadFacts() {
  try {
    const res = await fetch('/api/facts');
    const data = await res.json();
    renderStats(data);
    renderCards(data.facts);
  } catch (e) {
    document.getElementById('factsContainer').innerHTML = '<div style="color:var(--red);">加载事实失败: ' + e + '</div>';
  }
}

function renderStats(data) {
  document.getElementById('statTotal').innerText = data.total_count;
  const freshPercent = data.total_count > 0 ? Math.round((data.fresh_count / data.total_count) * 100) : 100;
  document.getElementById('statFreshRate').innerText = freshPercent + '%';
  document.getElementById('statWeijian').innerText = data.weijian_count;
  document.getElementById('statTransfer').innerText = data.transfer_count;
}

function renderCards(facts) {
  const container = document.getElementById('factsContainer');
  if (!facts || facts.length === 0) {
    container.innerHTML = '<div style="color:#8b949e; font-size:13px;">暂无事实记录，请使用下方表单录入。</div>';
    return;
  }
  container.innerHTML = facts.map(f => {
    const freshTag = f.is_fresh 
      ? `<span class="tag-fresh">🟢 保鲜中 (${f.age_days}天)</span>` 
      : `<span class="tag-stale">🟡 需保鲜 (已${f.age_days}天)</span>`;
    return `
      <div class="fact-card">
        <div class="fact-header">
          <div>
            <div class="fact-id">${f.entity_id}</div>
            <div class="fact-name">${f.name}</div>
          </div>
          ${freshTag}
        </div>
        <div class="fact-meta">
          <span>🏢 领域: <b>${f.domain}</b></span>
          <span>👤 责任: <b>${f.owner}</b></span>
          <span class="tag-stage">${f.lifecycle_stage}</span>
        </div>
        <div class="fact-body">${JSON.stringify(f.facts, null, 2)}</div>
      </div>
    `;
  }).join('');
}

function showToast(msg, isSuccess) {
  const toast = document.getElementById('toast');
  toast.innerText = msg;
  toast.className = isSuccess ? 'toast-success' : 'toast-error';
  toast.style.display = 'block';
  setTimeout(() => { toast.style.display = 'none'; }, 4000);
}

document.getElementById('factForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  let factsData = {};
  const rawText = document.getElementById('facts_json').value.trim();
  if (rawText) {
    try {
      factsData = JSON.parse(rawText);
    } catch (err) {
      showToast('事实 JSON 格式不合法，请检查', false);
      return;
    }
  }

  const payload = {
    schema_version: 'v1.0',
    entity_id: document.getElementById('entity_id').value.trim(),
    domain: document.getElementById('domain').value,
    name: document.getElementById('name').value.trim(),
    owner: document.getElementById('owner').value.trim(),
    lifecycle_stage: document.getElementById('lifecycle_stage').value,
    facts: factsData
  };

  try {
    const res = await fetch('/api/facts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (res.ok && result.success) {
      showToast('✅ 事实实体已成功写入并验证通过！', true);
      document.getElementById('factForm').reset();
      loadFacts();
    } else {
      showToast('❌ 写入失败: ' + (result.errors || []).join('; '), false);
    }
  } catch (err) {
    showToast('❌ 网络提交异常: ' + err, false);
  }
});

loadFacts();
</script>
</body>
</html>
"""


class TruthCanvasRequestHandler(http.server.BaseHTTPRequestHandler):
    facts_dir: Path = Path("/Users/xiamingxing/Documents/@工作文档")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(CANVAS_HTML_TEMPLATE.encode("utf-8"))
            return

        if parsed.path == "/api/facts":
            self._handle_api_get_facts()
            return

        if parsed.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy", "service": "truth-canvas-server"}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/facts":
            self._handle_api_post_facts()
            return

        self.send_response(404)
        self.end_headers()

    def _handle_api_get_facts(self) -> None:
        inspector = FactInspector(max_age_days=14)
        facts_res = inspector.inspect_directory(self.facts_dir)

        fact_cards: list[dict[str, Any]] = []
        weijian_count = 0
        transfer_count = 0
        fresh_count = 0

        for f in facts_res:
            if f.passed:
                if f.is_fresh:
                    fresh_count += 1
                if f.domain == "work-weijian":
                    weijian_count += 1
                elif f.domain == "work-transfer":
                    transfer_count += 1
                fact_cards.append(
                    {
                        "entity_id": f.entity_id,
                        "name": f.name,
                        "domain": f.domain,
                        "owner": f.owner,
                        "lifecycle_stage": f.lifecycle_stage,
                        "updated_at": f.updated_at,
                        "age_days": f.age_days,
                        "is_fresh": f.is_fresh,
                        "facts": f.facts_data,
                    }
                )

        payload = {
            "total_count": len(fact_cards),
            "fresh_count": fresh_count,
            "weijian_count": weijian_count,
            "transfer_count": transfer_count,
            "facts": fact_cards,
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _handle_api_post_facts(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            data = json.loads(body)
        except Exception as e:
            self._send_json_error(f"Invalid JSON payload: {e}", 400)
            return

        # Basic schema fields
        entity_id = data.get("entity_id", "").strip()
        if not entity_id:
            self._send_json_error("Missing required field: entity_id", 400)
            return

        from datetime import datetime, timezone

        if not data.get("updated_at"):
            data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Determine target file location
        domain = data.get("domain", "work-weijian")
        domain_sub = "卫健委" if domain == "work-weijian" else "国转中心"
        target_dir = self.facts_dir / domain_sub / "_entities" / "facts"
        os.makedirs(str(target_dir), exist_ok=True)
        target_file = target_dir / f"{entity_id.lower()}.yaml"

        yaml_content = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        with open(str(target_file), "w", encoding="utf-8") as f:
            f.write(yaml_content)

        # Validate with inspector
        inspector = FactInspector(max_age_days=14)
        inspect_res = inspector.inspect_file(target_file)
        if not inspect_res.passed:
            try:
                target_file.unlink()
            except Exception:
                pass
            self.send_response(422)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "success": False,
                        "errors": inspect_res.errors,
                    }
                ).encode("utf-8")
            )
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {
                    "success": True,
                    "entity_id": entity_id,
                    "file_path": str(target_file),
                    "is_fresh": inspect_res.is_fresh,
                }
            ).encode("utf-8")
        )

    def _send_json_error(self, message: str, status_code: int = 400) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"success": False, "errors": [message]}).encode("utf-8"))


def create_truth_canvas_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    facts_dir: Path | None = None,
) -> http.server.HTTPServer:
    """Create configured HTTPServer instance for truth canvas."""
    handler_class = TruthCanvasRequestHandler
    if facts_dir:
        handler_class.facts_dir = facts_dir
    return http.server.HTTPServer((host, port), handler_class)
