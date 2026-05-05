// frontend/app.js — Finance AI chat UI logic

const API    = 'http://localhost:8080';
const msgEl  = document.getElementById('messages');
const inputEl= document.getElementById('input');
const sendBtn= document.getElementById('send-btn');

// ── Auto-resize textarea ───────────────────────────────────────────────────
inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
});
inputEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});

// ── Health checks ──────────────────────────────────────────────────────────
async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`, { signal: AbortSignal.timeout(2500) });
    const d = await r.json();
    setDot('api', true);
    setDot('mcp', d.mcp_server === 'ok');
  } catch { setDot('api', false); setDot('mcp', false); }
  try {
    await fetch('http://localhost:11434', { signal: AbortSignal.timeout(2000), mode: 'no-cors' });
    setDot('llm', true);
  } catch { setDot('llm', false); }
}

function setDot(id, on) {
  document.getElementById('dot-' + id).className = 'dot ' + (on ? 'on' : 'off');
  const labels = { api: ['online','offline'], mcp: ['running','stopped'], llm: ['running','stopped'] };
  document.getElementById('lbl-' + id).textContent = on ? labels[id][0] : labels[id][1];
}

checkHealth();
setInterval(checkHealth, 6000);

// ── Quick query helper ─────────────────────────────────────────────────────
function ask(text) { inputEl.value = text; send(); }

// ── SSE status icon map ────────────────────────────────────────────────────
const STATUS_ICONS = {
  start: '🤖', thinking: '💭', planned: '📋',
  agent_start: '▶', agent_done: '✓', tool_call: '⚡',
  finish: '✅', error: '✕', done: '✓',
};

// ── Send message ───────────────────────────────────────────────────────────
async function send() {
  const text = inputEl.value.trim();
  if (!text) return;
  const cid = parseInt(document.getElementById('cid').value) || 1;

  // Remove welcome screen on first message
  const w = document.getElementById('welcome');
  if (w) w.remove();

  addUserMsg(text);
  inputEl.value = '';
  inputEl.style.height = 'auto';
  sendBtn.disabled = true;

  // Auto-detect customer ID mentioned in the message
  const mentioned = text.match(/(?:customer|cust|id)[\s#:]*?(\d+)/i);
  if (mentioned) document.getElementById('cid').value = mentioned[1];

  // Activity feed placeholder shown while streaming
  const feedDiv = document.createElement('div');
  feedDiv.className = 'msg ai';
  const feed = document.createElement('div');
  feed.className = 'activity-feed';
  feedDiv.appendChild(feed);
  msgEl.appendChild(feedDiv);
  scrollBottom();

  const url = `${API}/chat/stream?message=${encodeURIComponent(text)}&customer_id=${cid}`;
  const es = new EventSource(url);
  let completed = false;
  const traceSteps = [];  // collect all steps for the collapsible trace

  es.onmessage = (e) => {
    if (!e.data || e.data.trim() === '') return;

    let evt;
    try { evt = JSON.parse(e.data); }
    catch { return; }

    if (evt.status === 'done') {
      completed = true;
      es.close();
      feedDiv.remove();
      try {
        const data = JSON.parse(evt.detail);
        if (data.error) addErrorMsg(data.error);
        else {
          if (data.raw && !data.raw.trading && data.raw.holdings) {
            data.raw = { trading: { calculate_pnl: data.raw } };
          }
          data._trace = traceSteps;  // attach collected steps
          addAIMsg(data);
        }
      } catch { addErrorMsg('Could not parse response.'); }
      sendBtn.disabled = false;
      scrollBottom();
      return;
    }

    if (evt.status === 'error') {
      addStep(feed, 'error', '✕', evt.label, evt.detail, false);
      traceSteps.push({ status: 'error', label: evt.label, detail: evt.detail });
      return;
    }

    const icon     = STATUS_ICONS[evt.status] || '⚙';
    const isActive = ['thinking', 'agent_start', 'tool_call', 'routing', 'mcp_call', 'llm'].includes(evt.status);
    addStep(feed, evt.status, icon, evt.label, evt.detail, isActive);
    traceSteps.push({ status: evt.status, icon, label: evt.label, detail: evt.detail });
    scrollBottom();
  };

  es.onerror = () => {
    // EventSource fires onerror on real errors AND after normal close.
    // Only surface an error message if we never got a 'done' event.
    if (completed) return;

    fetch(`${API}/health`, { signal: AbortSignal.timeout(3000) })
      .then(r => {
        if (r.ok) {
          addErrorMsg('The request timed out — the AI tool took too long.\nTry again or ask a simpler question.');
        } else {
          addErrorMsg('API server returned an error. Check the server terminal.');
        }
      })
      .catch(() => {
        addErrorMsg(
          'Cannot reach API server.\n' +
          'Make sure it is running:\n' +
          '  PYTHONPATH=. python3.12 -m uvicorn client.main:app --reload --port 8080'
        );
      })
      .finally(() => {
        feedDiv.remove();
        sendBtn.disabled = false;
        scrollBottom();
      });
  };
}

// ── Activity step renderer ─────────────────────────────────────────────────
function addStep(feed, status, icon, label, detail, isActive) {
  // Mark previous active step as done
  feed.querySelectorAll('.activity-step.active').forEach(s => {
    s.classList.remove('active');
    s.classList.add('done-step');
    const sp = s.querySelector('.step-spinner');
    if (sp) sp.outerHTML = '<span style="color:var(--green);font-size:12px">✓</span>';
  });

  const step = document.createElement('div');
  const cls  = status === 'error' ? 'error-step' : isActive ? 'active' : 'done-step';
  step.className = `activity-step ${cls}`;
  step.innerHTML = `
    <span class="step-icon">${icon}</span>
    <span class="step-label">${esc(label)}</span>
    ${detail ? `<span class="step-detail">${esc(detail)}</span>` : ''}
    ${isActive ? '<div class="step-spinner"></div>' : ''}
  `;
  feed.appendChild(step);
}

// ── Message renderers ──────────────────────────────────────────────────────
function addUserMsg(text) {
  const div = document.createElement('div');
  div.className = 'msg user';
  div.innerHTML = `<div class="bubble">${esc(text)}</div>`;
  msgEl.appendChild(div);
  scrollBottom();
}

function addAIMsg(data) {
  const time   = new Date().toLocaleTimeString('en-GB', { hour12: false });
  const tool   = data.mcp_tool || '';
  const reply  = data.reply || 'No response.';
  const raw    = JSON.stringify(data.raw || {}, null, 2);
  const uid    = 'r' + Date.now();
  const tid    = 'trace' + Date.now();
  const agents = data.agents_called ? data.agents_called.join(', ') : '';
  const trace  = data._trace || [];

  const pnlHtml = renderPnL(data.raw);

  // Build collapsible trace — SSE steps + rich breakdown from raw data
  const traceRows = buildTraceHtml(trace, data.raw);
  const traceCount = trace.length;

  const tracePanel = traceCount ? `
    <div class="trace-toggle" onclick="toggleRaw('${tid}')">
      <span id="arr-${tid}">▶</span> Agent trace (${traceCount} steps)
    </div>
    <div class="raw-block trace-block" id="${tid}">${traceRows}</div>
  ` : '';

  const div = document.createElement('div');
  div.className = 'msg ai';
  div.innerHTML = `
    <div class="bubble">
      <div class="tool-badge">⚙ ${esc(tool)}${agents ? ' · ' + esc(agents) : ''}</div>
      ${tracePanel}
      <div class="report">${pnlHtml || formatReport(reply)}</div>
      <div class="raw-toggle" onclick="toggleRaw('${uid}')">
        <span id="arr-${uid}">▶</span> Raw data
      </div>
      <div class="raw-block" id="${uid}">${esc(raw)}</div>
    </div>
    <div class="bubble-meta">${time}${data.tool_calls ? ' · ' + data.tool_calls + ' tool calls' : ''}</div>
  `;
  msgEl.appendChild(div);
  scrollBottom();
}

/**
 * Build a rich HTML trace combining:
 * 1. SSE steps (routing, MCP call, etc.)
 * 2. Structured breakdown from raw data (agents, tools, results, flags)
 */
function buildTraceHtml(steps, raw) {
  let html = '';

  // ── Section 1: MCP protocol steps ────────────────────────────────────────
  html += traceHeader('🔌 MCP Protocol');
  steps.forEach(s => {
    const isErr = s.status === 'error';
    html += traceRow(isErr ? '✕' : '✓', s.label, s.detail, isErr ? 'error' : 'ok');
  });

  if (!raw || typeof raw !== 'object') return html;

  // ── Section 2: Agents & tools called ─────────────────────────────────────
  // Detect which domains were touched from the raw keys
  const domains = {
    'Customer':  raw.profile   ? { icon: '👤', tools: [['get_customer_profile',  raw.profile]] } : null,
    'Loan':      raw.credit    ? { icon: '🏦', tools: [
                                    ['credit_score_tool',  raw.credit],
                                    raw.loans?.length ? ['check_loan_status', raw.loans] : null,
                                  ].filter(Boolean) } : null,
    'Risk':      raw.risk      ? { icon: '⚠️', tools: [
                                    ['risk_score_tool',  raw.risk],
                                    raw.fraud ? ['fraud_check_tool', raw.fraud] : null,
                                  ].filter(Boolean) } : null,
    'Trading':   raw.portfolio_pnl ? { icon: '📈', tools: [
                                    ['get_portfolio',    raw.portfolio_pnl.holdings],
                                    ['calculate_pnl',   raw.portfolio_pnl],
                                  ] } : null,
  };

  const activeDomains = Object.entries(domains).filter(([, v]) => v);
  if (activeDomains.length) {
    html += traceHeader(`🤖 Agents Called (${activeDomains.length})`);
    activeDomains.forEach(([name, { icon, tools }]) => {
      html += traceRow(icon, `${name} Agent`, `${tools.length} tool(s)`, 'agent');
      tools.forEach(([toolName]) => {
        html += traceRow('⚡', toolName, '', 'tool');
      });
    });
  }

  return html;
}

function traceHeader(label) {
  return `<div class="trace-section-header">${label}</div>`;
}

function traceRow(icon, label, detail, type = 'ok') {
  const colors = {
    ok:     'var(--green)',
    green:  'var(--green)',
    amber:  'var(--amber)',
    red:    'var(--red)',
    error:  'var(--red)',
    agent:  'var(--accent)',
    tool:   'var(--text-dim)',
    muted:  'var(--text-faint)',
  };
  const borderColor = colors[type] || 'var(--border)';
  const isIndented  = type === 'tool' || type === 'muted';
  return `
    <div class="trace-step ${type === 'error' ? 'trace-step-error' : 'trace-step-done'}"
         style="border-left-color:${borderColor}; ${isIndented ? 'margin-left:18px; opacity:0.85;' : ''}">
      <span class="trace-icon">${icon}</span>
      <span class="trace-label">${esc(label)}</span>
      ${detail ? `<span class="trace-detail">${esc(detail)}</span>` : ''}
    </div>`;
}

function renderPnL(raw) {
  const holdings = raw?.trading?.calculate_pnl?.holdings;
  const totalPnl  = raw?.trading?.calculate_pnl?.total_pnl;
  if (!holdings || !holdings.length) return null;

  const fmt  = (n) => '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sign  = (n) => n >= 0 ? '+' : '−';
  const color = (n) => n >= 0 ? 'var(--green)' : 'var(--red)';
  const arrow = (n) => n >= 0 ? '▲' : '▼';

  let rows = holdings.map(h => {
    const pnl        = h.pnl;
    const pctChange  = ((h.current_price - h.avg_price) / h.avg_price * 100).toFixed(1);
    const pnlColor   = color(pnl);

    return `
      <div class="pnl-row">
        <span class="pnl-symbol">${esc(h.symbol)}</span>
        <span class="pnl-qty">${h.quantity} shares</span>
        <span class="pnl-prices">
          <span class="pnl-avg">avg ${fmt(h.avg_price)}</span>
          <span class="pnl-arrow">→</span>
          <span class="pnl-cur">${fmt(h.current_price)}</span>
        </span>
        <span class="pnl-value" style="color:${pnlColor}">
          ${arrow(pnl)} ${sign(pnl)}${fmt(pnl)}
          <span class="pnl-pct">(${sign(pnl)}${Math.abs(pctChange)}%)</span>
        </span>
      </div>`;
  }).join('');

  const totalColor = color(totalPnl);
  const totalSign  = sign(totalPnl);
  const totalArrow = arrow(totalPnl);

  return `
    <div class="report-section-header">📈 PORTFOLIO P&amp;L</div>
    <div class="pnl-table">${rows}</div>
    <div class="pnl-total" style="border-top:1px solid var(--border); margin-top:10px; padding-top:10px;">
      <span style="font-weight:600; font-size:12px; color:var(--text)">Total unrealised</span>
      <span style="font-weight:700; font-size:15px; color:${totalColor}; margin-left:auto">
        ${totalArrow} ${totalSign}${fmt(totalPnl)}
      </span>
    </div>`;
}

function addErrorMsg(text) {
  const div = document.createElement('div');
  div.className = 'msg error';
  div.innerHTML = `<div class="bubble">${esc(text)}</div>`;
  msgEl.appendChild(div);
  scrollBottom();
}

function toggleRaw(id) {
  const b = document.getElementById(id);
  const a = document.getElementById('arr-' + id);
  b.classList.toggle('open');
  a.textContent = b.classList.contains('open') ? '▼' : '▶';
}

// ── Helpers ────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;')
    .replace(/\n/g,'<br>');
}

/**
 * Format a plain-text agent reply into HTML report sections.
 * Detects structured reports (emoji section headers like 👤 CUSTOMER)
 * and renders them as labeled key-value rows. Falls back to plain text.
 */
function formatReport(text) {
  if (!text) return '';

  const isReport = /[👤🏦⚠️📈]\s+[A-Z]/.test(text);
  if (!isReport) {
    return esc(text).replace(/\n/g, '<br>');
  }

  const sections = text.split(/\n\n+/);
  let html = '';

  for (const section of sections) {
    const lines = section.split('\n').filter(l => l.trim());
    if (!lines.length) continue;

    const firstLine = lines[0];
    const isHeader  = /^[👤🏦⚠️📈🔍💰📋]/.test(firstLine);

    if (isHeader) {
      html += '<div class="report-section">';
      html += `<div class="report-section-header">${esc(firstLine)}</div>`;

      for (let i = 1; i < lines.length; i++) {
        const line  = lines[i];
        const match = line.match(/^\s+(\S[^:]{2,20}):\s+(.*)/);
        if (match) {
          html += `<div class="report-row"><span class="rk">${esc(match[1])}</span><span class="rv">${esc(match[2])}</span></div>`;
        } else {
          html += `<div class="report-row"><span class="rk"></span><span class="rv">${esc(line.trim())}</span></div>`;
        }
      }
      html += '</div>';
    } else {
      html += `<div class="report-plain">${esc(section).replace(/\n/g, '<br>')}</div>`;
    }
  }

  return html || esc(text).replace(/\n/g, '<br>');
}

function scrollBottom() { msgEl.scrollTop = msgEl.scrollHeight; }