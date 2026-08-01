const token = document.querySelector('meta[name="lightworker-token"]').content;
const state = { tasks: [], status: '', search: '', selected: null, doctor: null };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

async function api(path, options = {}) {
  const headers = { Accept: 'application/json', ...(options.headers || {}) };
  if (options.body) headers['Content-Type'] = 'application/json';
  if ((options.method || 'GET') !== 'GET') headers['X-LightWorker-Token'] = token;
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function toast(message, error = false) {
  const node = $('#toast');
  node.textContent = message;
  node.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.className = 'toast'; }, 3400);
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
}

function formatTime(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(value));
}

function roleLabel(kind) {
  return ({ plan: 'Planner', explore: 'Explorer', execute: 'Executor', review: 'Reviewer' })[kind] || kind;
}

function statusLabel(status) {
  return ({ queued: '等待调度', starting: '正在启动', running: '正在运行', awaiting_approval: '需要审批', completed: '已完成', failed: '失败', cancelled: '已取消', blocked: '已阻塞', orphaned: '已孤立' })[status] || status;
}

function updateMetrics() {
  const counts = Object.fromEntries(['queued', 'starting', 'running', 'awaiting_approval', 'completed', 'failed', 'blocked', 'cancelled', 'orphaned'].map((key) => [key, state.tasks.filter((task) => task.status === key).length]));
  const active = counts.running + counts.starting;
  const finished = counts.completed + counts.failed + counts.blocked + counts.cancelled + counts.orphaned;
  $('#metric-total').textContent = state.tasks.length;
  $('#metric-active').textContent = active;
  $('#metric-approval').textContent = counts.awaiting_approval;
  $('#metric-rate').textContent = finished ? `${Math.round(counts.completed / finished * 100)}%` : '—';
  $('#metric-capacity').textContent = `并发上限 ${state.doctor?.max_concurrency ?? 2}`;
  $('#nav-all').textContent = state.tasks.length;
  $('#nav-running').textContent = active;
  $('#nav-queued').textContent = counts.queued;
  $('#nav-approval').textContent = counts.awaiting_approval;
  $('#nav-completed').textContent = counts.completed;
  $('#nav-failed').textContent = counts.failed + counts.blocked + counts.orphaned;
}

function renderTasks() {
  const query = state.search.toLowerCase();
  const tasks = state.tasks.filter((task) => {
    const statusMatch = !state.status || task.status === state.status || (state.status === 'running' && task.status === 'starting') || (state.status === 'failed' && ['failed', 'blocked', 'orphaned'].includes(task.status));
    const text = `${task.id} ${task.objective} ${task.model} ${task.kind}`.toLowerCase();
    return statusMatch && (!query || text.includes(query));
  });
  $('#empty-state').hidden = tasks.length > 0;
  $('#task-body').innerHTML = tasks.map((task) => `
    <tr data-task-id="${escapeHtml(task.id)}">
      <td class="task-name"><strong title="${escapeHtml(task.objective)}">${escapeHtml(task.objective)}</strong><small>${escapeHtml(task.id)}</small></td>
      <td class="model-cell"><span>${escapeHtml(roleLabel(task.kind))}</span><small>${escapeHtml(task.model)}</small></td>
      <td><span class="status ${escapeHtml(task.status)}">${escapeHtml(statusLabel(task.status))}</span></td>
      <td>${escapeHtml(formatTime(task.created_at))}</td>
      <td><button class="row-action" data-open-task="${escapeHtml(task.id)}">查看</button></td>
    </tr>`).join('');
}

function populateModels() {
  const models = state.doctor?.allowed_models || [];
  for (const id of ['orchestrate-model', 'single-model']) {
    const select = $(`#${id}`);
    const previous = select.value;
    const automatic = id === 'single-model'
      ? '<option value="">自动路由：low → DeepSeek Flash；其余 → GPT-5.6 Sol</option>'
      : '';
    select.innerHTML = automatic + models.map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`).join('');
    const preferred = id === 'orchestrate-model' ? 'gpt-5.6-sol' : '';
    select.value = models.includes(previous) || previous === '' ? previous : preferred;
  }
}

function updateHealth() {
  const node = $('#proxy-health');
  const healthy = Boolean(
    state.doctor?.codex_path &&
    state.doctor?.cliproxyapi_8317 &&
    state.doctor?.opencodex_proxy_10100
  );
  const scheduler = state.doctor?.scheduler_role === 'active' ? '调度运行中' : '调度待命';
  node.className = `health-chip ${healthy ? 'ok' : 'bad'}`;
  node.lastChild.textContent = healthy ? `代理在线 · ${scheduler}` : 'Codex 或代理连接异常';
}

async function refresh(silent = false) {
  try {
    const [doctor, tasks] = await Promise.all([api('/api/doctor'), api('/api/tasks?limit=500')]);
    state.doctor = doctor;
    state.tasks = tasks.tasks;
    updateMetrics();
    renderTasks();
    updateHealth();
    populateModels();
    if (state.selected) await loadTask(state.selected, true);
    if (!silent) toast('任务状态已刷新');
  } catch (error) {
    updateHealth();
    if (!silent) toast(error.message, true);
  }
}

async function loadTask(taskId, silent = false) {
  try {
    const [task, events] = await Promise.all([api(`/api/tasks/${encodeURIComponent(taskId)}`), api(`/api/tasks/${encodeURIComponent(taskId)}/events?limit=120`)]);
    state.selected = taskId;
    $('#task-drawer').classList.add('open');
    $('#task-drawer').setAttribute('aria-hidden', 'false');
    $('#drawer-backdrop').hidden = false;
    $('#detail-kind').textContent = roleLabel(task.kind);
    $('#detail-title').textContent = task.name || task.id;
    $('#detail-objective').textContent = task.objective;
    $('#detail-meta').innerHTML = [task.status, task.model, task.sandbox, formatTime(task.created_at), task.worktree_path].filter(Boolean).map((value) => `<span>${escapeHtml(value)}</span>`).join('');
    const actions = [];
    if (task.status === 'awaiting_approval') actions.push(`<button class="button approve" data-approve="${escapeHtml(task.id)}">批准执行</button>`);
    if (!['completed', 'failed', 'cancelled', 'blocked', 'orphaned'].includes(task.status)) actions.push(`<button class="button danger" data-cancel="${escapeHtml(task.id)}">取消任务</button>`);
    $('#detail-actions').innerHTML = actions.join('');
    $('#detail-result').textContent = task.result ? JSON.stringify(task.result, null, 2) : (task.error || '等待 Worker 返回…');
    $('#detail-events').innerHTML = events.events.slice().reverse().map((event) => `<div class="event"><strong>${escapeHtml(event.event_type)}</strong><small>${escapeHtml(formatTime(event.created_at))}</small></div>`).join('') || '<p class="objective">暂无事件</p>';
  } catch (error) {
    if (!silent) toast(error.message, true);
  }
}

function closeDrawer() {
  state.selected = null;
  $('#task-drawer').classList.remove('open');
  $('#task-drawer').setAttribute('aria-hidden', 'true');
  $('#drawer-backdrop').hidden = true;
}

async function submitOrchestration() {
  const payload = {
    objective: $('#orchestrate-objective').value.trim(),
    workspace: $('#orchestrate-workspace').value.trim(),
    mode: $('#orchestrate-mode').value,
    model: $('#orchestrate-model').value,
    max_tasks: Number($('#orchestrate-max').value),
  };
  if (!payload.objective || !payload.workspace) return toast('请填写目标和工作区', true);
  try {
    const result = await api('/api/orchestrate', { method: 'POST', body: JSON.stringify(payload) });
    $('#task-dialog').close();
    toast(`规划任务已入队：${result.root_task_id}`);
    await refresh(true);
    await loadTask(result.root_task_id);
  } catch (error) { toast(error.message, true); }
}

async function submitSingle() {
  const success = $('#single-success').value.trim();
  const payload = {
    objective: $('#single-objective').value.trim(),
    workspace: $('#single-workspace').value.trim(),
    kind: $('#single-kind').value,
    model: $('#single-model').value,
    reasoning_effort: $('#single-effort').value,
    mode: $('#single-mode').value,
    timeout_seconds: Number($('#single-timeout').value),
    success_criteria: success ? [success] : [],
  };
  if (!payload.objective || !payload.workspace) return toast('请填写目标和工作区', true);
  try {
    const result = await api('/api/tasks', { method: 'POST', body: JSON.stringify(payload) });
    $('#task-dialog').close();
    toast(`Worker 已入队：${result.task_id}`);
    await refresh(true);
    await loadTask(result.task_id);
  } catch (error) { toast(error.message, true); }
}

document.addEventListener('click', async (event) => {
  const open = event.target.closest('[data-open-task]');
  if (open) return loadTask(open.dataset.openTask);
  const approve = event.target.closest('[data-approve]');
  if (approve) {
    try { await api(`/api/tasks/${encodeURIComponent(approve.dataset.approve)}/approve`, { method: 'POST', body: '{}' }); toast('任务已批准'); await refresh(true); } catch (error) { toast(error.message, true); }
  }
  const cancel = event.target.closest('[data-cancel]');
  if (cancel && confirm('确定取消这个任务吗？')) {
    try { await api(`/api/tasks/${encodeURIComponent(cancel.dataset.cancel)}/cancel`, { method: 'POST', body: '{}' }); toast('已发送取消请求'); await refresh(true); } catch (error) { toast(error.message, true); }
  }
});

$$('.nav-item').forEach((button) => button.addEventListener('click', () => {
  $$('.nav-item').forEach((item) => item.classList.remove('active'));
  button.classList.add('active');
  state.status = button.dataset.status;
  renderTasks();
}));
$$('.tab').forEach((button) => button.addEventListener('click', () => {
  $$('.tab').forEach((item) => item.classList.toggle('active', item === button));
  $$('.tab-pane').forEach((pane) => pane.classList.toggle('active', pane.id === `pane-${button.dataset.tab}`));
}));
$('#search-input').addEventListener('input', (event) => { state.search = event.target.value; renderTasks(); });
$('#new-task-button').addEventListener('click', () => $('#task-dialog').showModal());
$('#refresh-button').addEventListener('click', () => refresh());
$('#submit-orchestrate').addEventListener('click', submitOrchestration);
$('#submit-single').addEventListener('click', submitSingle);
$('#close-task-dialog').addEventListener('click', () => $('#task-dialog').close());
$('#close-drawer').addEventListener('click', closeDrawer);
$('#drawer-backdrop').addEventListener('click', closeDrawer);
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeDrawer(); });

refresh(true);
setInterval(() => { if (!document.hidden) refresh(true); }, 3000);
