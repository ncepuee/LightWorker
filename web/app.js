const token = document.querySelector('meta[name="lightworker-token"]').content;
const state = { tasks: [], status: '', search: '', selected: null, doctor: null, cache: null, view: localStorage.getItem('lw-view') || 'board' };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const I18N = {
  zh: {
    'nav.filter': '任务状态过滤', 'nav.all': '全部任务', 'nav.running': '正在运行', 'nav.queued': '等待调度', 'nav.approval': '需要审批', 'nav.completed': '已完成', 'nav.failed': '异常任务',
    'note.eyebrow': '安全模式', 'note.title': '默认只读', 'note.body': '写任务进入独立 worktree，并在 auto_readonly 下等待审批。',
    'top.eyebrow': '本地协作编排', 'top.title': '任务控制台', 'top.version': 'LightWorker 当前版本', 'top.checking': '正在检查代理', 'top.purge': '清空历史', 'top.refresh': '刷新', 'top.new': '新建任务',
    'metrics.label': '任务统计', 'metrics.total': '任务总数', 'metrics.totalSub': '当前状态库', 'metrics.active': '活跃 Worker', 'metrics.approval': '待审批', 'metrics.approvalSub': '写入前人工确认', 'metrics.rate': '完成率', 'metrics.rateSub': '排除排队任务', 'metrics.cache': 'DeepSeek 暖缓存', 'metrics.gateway': '网关状态', 'metrics.gatewaySub': '连接成功才可委派任务',
    'cache.title': 'DeepSeek 缓存 Cohort', 'cache.waiting': '等待样本', 'cache.colPath': '路径 / 模型', 'cache.colStatus': '状态', 'cache.colSamples': '样本', 'cache.colHit': '命中率',
    'board.title': '协作任务', 'board.search': '搜索目标、模型或任务 ID', 'board.viewBoard': '看板视图', 'board.viewList': '列表视图', 'board.board': '▦ 看板', 'board.list': '☰ 列表',
    'board.colTask': '任务', 'board.colRole': '角色 / 模型', 'board.colStatus': '状态', 'board.colTime': '创建时间', 'board.colAction': '操作', 'board.empty': '暂时没有任务', 'board.emptySub': '创建一个自动规划目标，或提交单个只读 Worker。',
    'dlg.title': '创建协作任务', 'dlg.tabOrch': '自动规划', 'dlg.tabSingle': '单个 Worker', 'dlg.objective': '目标', 'dlg.objectivePh': '例如：检查登录模块的可靠性，拆成并行只读调查并汇总证据。',
    'dlg.workspace': '工作区', 'dlg.mode': '执行模式', 'dlg.modeAutoReadonly': 'auto_readonly（推荐）', 'dlg.plannerModel': 'Planner 模型', 'dlg.plannerProfile': 'Planner Profile', 'dlg.gateway': '网关', 'dlg.maxSub': '最大子任务',
    'dlg.contextPack': '共享 Context Pack（可选，最多 32KiB）', 'dlg.contextPackPh': '仅填写多次任务都需要的稳定、已审阅上下文；不要填密钥或动态日志。', 'dlg.submitOrch': '生成任务 DAG',
    'dlg.singleObjective': '任务目标', 'dlg.singleObjectivePh': '给 Worker 一个边界清楚、可验证的目标。', 'dlg.kind': '角色', 'dlg.workerProfile': 'Worker Profile', 'dlg.model': '模型', 'dlg.channel': '执行通道',
    'dlg.channelNative': 'OpenCodex 原生子代理', 'dlg.capabilities': '所需能力', 'dlg.capabilitiesPh': '例如：web_search', 'dlg.effort': '推理强度', 'dlg.effortAuto': '按 Profile / 自动路由', 'dlg.timeout': '超时（秒）',
    'dlg.success': '成功条件', 'dlg.successPh': '例如：列出文件证据并给出可复现命令', 'dlg.contextPackPh2': '相同 Cohort 的 Worker 使用完全相同的稳定上下文。', 'dlg.submitSingle': '提交 Worker',
    'detail.title': '任务详情', 'detail.objective': '目标', 'detail.route': '路由审计', 'detail.governance': '预算与 Schema', 'detail.result': '结构化结果', 'detail.events': '事件时间线', 'common.close': '关闭',
    'col.queued': '队列中', 'col.running': '进行中', 'col.awaiting_approval': '待审批', 'col.completed': '已完成', 'col.failed': '异常',
    'kanban.empty': '暂无任务',
    'status.queued': '等待调度', 'status.starting': '正在启动', 'status.running': '正在运行', 'status.awaiting_approval': '需要审批', 'status.completed': '已完成', 'status.failed': '失败', 'status.cancelled': '已取消', 'status.blocked': '已阻塞', 'status.orphaned': '已孤立',
    'role.plan': 'Planner', 'role.explore': 'Explorer', 'role.execute': 'Executor', 'role.review': 'Reviewer',
    'action.view': '查看', 'action.approve': '批准当前权限范围', 'action.cancel': '取消任务', 'action.fallback': '改用 {gw} 重试', 'action.escalate': '升级到深度 Worker',
    'health.schedulerActive': '调度运行中', 'health.schedulerIdle': '调度待命', 'health.online': '代理在线 · {s}', 'health.offline': 'Codex 或代理连接异常',
    'top.overallHealth': '整体健康状态', 'gw.connected': '已连接', 'gw.disconnected': '未连接', 'gw.absent': '未配置', 'gw.needGateway': '至少一个网关连接成功才能委派任务', 'gw.checking': '检查中', 'gw.online': '在线', 'gw.offline': '离线',
    'toast.refreshed': '任务状态已刷新', 'toast.needObjective': '请填写目标和工作区', 'toast.orchQueued': '规划任务已入队：{id}', 'toast.workerQueued': 'Worker 已入队：{id}', 'toast.approved': '当前权限范围已批准',
    'toast.cancelSent': '已发送取消请求', 'toast.fallbackQueued': '备用任务已入队：{id}', 'toast.escalateQueued': '升级任务已入队：{id}', 'toast.purged': '已清空 {n} 条历史任务',
    'confirm.cancel': '确定取消这个任务吗？', 'confirm.fallback': '创建一个新的只读任务并改用备用网关？原任务会保留。', 'confirm.escalate': '创建一个新的只读深度 Worker 尝试？原任务和原始结果会保留。',
    'confirm.purge': '确定清空所有已结束的历史任务吗？\n\n将删除：已完成、失败、已阻塞、已孤立、已取消的任务及其事件与用量记录。\n排队中、运行中、待审批的任务不会被删除。此操作不可恢复。',
    'detail.waitingRoute': '等待调度…', 'detail.noRoute': '旧任务没有路由审计数据', 'detail.noGovernance': '尚无运行数据…', 'detail.waitingWorker': '等待 Worker 返回…', 'detail.noEvents': '暂无事件',
    'meta.model': '模型', 'meta.provider': '提供方', 'meta.upstream': '上游', 'meta.gateway': '网关', 'meta.channel': '通道', 'meta.verified': '核验', 'meta.fallback': '备用',
    'opt.autoRoute': '按 Profile / 自动路由', 'opt.noProfile': '不指定 Profile', 'opt.autoGateway': '按模型自动选择（推荐）', 'opt.notRoutable': ' · 当前不可路由',
    'cache.noSamples': '尚无可用缓存样本', 'cache.insufficient': '样本不足', 'cache.warmSamples': '{n} 个暖样本 · {v} 已核验（达标按单一 cohort）',
    'cache.achieved': '已达到 {r}目标', 'cache.below': '尚未达到目标', 'cache.unverified': '路由未核验', 'cache.verified': 'verified', 'cache.unverifiedMark': '—（未核验）',
    'protocol.native': 'Native Responses', 'protocol.translated': 'Responses → Chat 转译',
    'lang.switched': '已切换为中文',
  },
  en: {
    'nav.filter': 'Filter by status', 'nav.all': 'All Tasks', 'nav.running': 'Running', 'nav.queued': 'Queued', 'nav.approval': 'Needs Approval', 'nav.completed': 'Completed', 'nav.failed': 'Failed',
    'note.eyebrow': 'Safe Mode', 'note.title': 'Read-only by default', 'note.body': 'Write tasks run in an isolated worktree and await approval under auto_readonly.',
    'top.eyebrow': 'Local Collaboration Orchestration', 'top.title': 'Task Console', 'top.version': 'LightWorker current version', 'top.checking': 'Checking proxy', 'top.purge': 'Clear History', 'top.refresh': 'Refresh', 'top.new': 'New Task',
    'metrics.label': 'Task statistics', 'metrics.total': 'Total Tasks', 'metrics.totalSub': 'Current state store', 'metrics.active': 'Active Workers', 'metrics.approval': 'Pending Approval', 'metrics.approvalSub': 'Manual confirm before write', 'metrics.rate': 'Completion Rate', 'metrics.rateSub': 'Excludes queued tasks', 'metrics.cache': 'DeepSeek Warm Cache', 'metrics.gateway': 'Gateway Status', 'metrics.gatewaySub': 'Delegation requires a connected gateway',
    'cache.title': 'DeepSeek Cache Cohort', 'cache.waiting': 'Waiting for samples', 'cache.colPath': 'Path / Model', 'cache.colStatus': 'Status', 'cache.colSamples': 'Samples', 'cache.colHit': 'Hit Rate',
    'board.title': 'Collaboration Tasks', 'board.search': 'Search objective, model or task ID', 'board.viewBoard': 'Board view', 'board.viewList': 'List view', 'board.board': '▦ Board', 'board.list': '☰ List',
    'board.colTask': 'Task', 'board.colRole': 'Role / Model', 'board.colStatus': 'Status', 'board.colTime': 'Created', 'board.colAction': 'Actions', 'board.empty': 'No tasks yet', 'board.emptySub': 'Create an auto-planned objective, or submit a single read-only worker.',
    'dlg.title': 'Create Collaboration Task', 'dlg.tabOrch': 'Auto Plan', 'dlg.tabSingle': 'Single Worker', 'dlg.objective': 'Objective', 'dlg.objectivePh': 'e.g. Review the login module reliability, split into parallel read-only investigations and summarize evidence.',
    'dlg.workspace': 'Workspace', 'dlg.mode': 'Mode', 'dlg.modeAutoReadonly': 'auto_readonly (recommended)', 'dlg.plannerModel': 'Planner Model', 'dlg.plannerProfile': 'Planner Profile', 'dlg.gateway': 'Gateway', 'dlg.maxSub': 'Max Subtasks',
    'dlg.contextPack': 'Shared Context Pack (optional, up to 32KiB)', 'dlg.contextPackPh': 'Only stable, reviewed context reused across tasks; do not include secrets or dynamic logs.', 'dlg.submitOrch': 'Generate Task DAG',
    'dlg.singleObjective': 'Task Objective', 'dlg.singleObjectivePh': 'Give the worker a well-bounded, verifiable objective.', 'dlg.kind': 'Role', 'dlg.workerProfile': 'Worker Profile', 'dlg.model': 'Model', 'dlg.channel': 'Execution Channel',
    'dlg.channelNative': 'OpenCodex native subagent', 'dlg.capabilities': 'Required Capabilities', 'dlg.capabilitiesPh': 'e.g. web_search', 'dlg.effort': 'Reasoning Effort', 'dlg.effortAuto': 'By Profile / auto route', 'dlg.timeout': 'Timeout (s)',
    'dlg.success': 'Success Criteria', 'dlg.successPh': 'e.g. List file evidence and give a reproducible command', 'dlg.contextPackPh2': 'Workers in the same cohort use identical stable context.', 'dlg.submitSingle': 'Submit Worker',
    'detail.title': 'Task Details', 'detail.objective': 'Objective', 'detail.route': 'Route Audit', 'detail.governance': 'Budget & Schema', 'detail.result': 'Structured Result', 'detail.events': 'Event Timeline', 'common.close': 'Close',
    'col.queued': 'Queued', 'col.running': 'Running', 'col.awaiting_approval': 'Approval', 'col.completed': 'Done', 'col.failed': 'Failed',
    'kanban.empty': 'No tasks',
    'status.queued': 'Queued', 'status.starting': 'Starting', 'status.running': 'Running', 'status.awaiting_approval': 'Needs Approval', 'status.completed': 'Completed', 'status.failed': 'Failed', 'status.cancelled': 'Cancelled', 'status.blocked': 'Blocked', 'status.orphaned': 'Orphaned',
    'role.plan': 'Planner', 'role.explore': 'Explorer', 'role.execute': 'Executor', 'role.review': 'Reviewer',
    'action.view': 'View', 'action.approve': 'Approve current scope', 'action.cancel': 'Cancel task', 'action.fallback': 'Retry via {gw}', 'action.escalate': 'Escalate to deep Worker',
    'health.schedulerActive': 'scheduler active', 'health.schedulerIdle': 'scheduler idle', 'health.online': 'Proxy online · {s}', 'health.offline': 'Codex or proxy connection error',
    'top.overallHealth': 'Overall health', 'gw.connected': 'Connected', 'gw.disconnected': 'Disconnected', 'gw.absent': 'Not configured', 'gw.needGateway': 'At least one gateway must be connected to delegate tasks', 'gw.checking': 'Checking', 'gw.online': 'Online', 'gw.offline': 'Offline',
    'toast.refreshed': 'Task state refreshed', 'toast.needObjective': 'Please fill in objective and workspace', 'toast.orchQueued': 'Plan task queued: {id}', 'toast.workerQueued': 'Worker queued: {id}', 'toast.approved': 'Current scope approved',
    'toast.cancelSent': 'Cancel request sent', 'toast.fallbackQueued': 'Fallback task queued: {id}', 'toast.escalateQueued': 'Escalation queued: {id}', 'toast.purged': 'Cleared {n} historical tasks',
    'confirm.cancel': 'Cancel this task?', 'confirm.fallback': 'Create a new read-only task using the fallback gateway? The original task is kept.', 'confirm.escalate': 'Create a new read-only deep Worker attempt? Original task and result are kept.',
    'confirm.purge': 'Clear all finished historical tasks?\n\nWill delete: completed, failed, blocked, orphaned, cancelled tasks with their events and usage records.\nQueued, running and pending-approval tasks are kept. This cannot be undone.',
    'detail.waitingRoute': 'Waiting to schedule…', 'detail.noRoute': 'Legacy task has no route audit data', 'detail.noGovernance': 'No run data yet…', 'detail.waitingWorker': 'Waiting for worker to return…', 'detail.noEvents': 'No events',
    'meta.model': 'Model', 'meta.provider': 'Provider', 'meta.upstream': 'Upstream', 'meta.gateway': 'Gateway', 'meta.channel': 'Channel', 'meta.verified': 'Verified', 'meta.fallback': 'Fallback',
    'opt.autoRoute': 'By Profile / auto route', 'opt.noProfile': 'No profile', 'opt.autoGateway': 'Auto by model (recommended)', 'opt.notRoutable': ' · not routable',
    'cache.noSamples': 'No cache samples available', 'cache.insufficient': 'Insufficient samples', 'cache.warmSamples': '{n} warm samples · {v} verified (target by single cohort)',
    'cache.achieved': 'Reached {r}target', 'cache.below': 'Below target', 'cache.unverified': 'Route unverified', 'cache.verified': 'verified', 'cache.unverifiedMark': '— (unverified)',
    'protocol.native': 'Native Responses', 'protocol.translated': 'Responses → Chat translated',
    'lang.switched': 'Switched to English',
  },
};
state.lang = localStorage.getItem('lw-lang') || 'zh';
function t(key, vars) {
  let s = (I18N[state.lang] && I18N[state.lang][key]) ?? I18N.zh[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
  return s;
}
function applyI18n() {
  document.documentElement.lang = state.lang === 'zh' ? 'zh-CN' : 'en';
  document.title = `LightWorker v${document.title.match(/v([\d.]+)/)?.[1] || ''}`.trim();
  $$('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $$('[data-i18n-ph]').forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  $$('[data-i18n-title]').forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  $$('[data-i18n-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
  $$('.lang-btn').forEach((btn) => btn.classList.toggle('active', btn.dataset.lang === state.lang));
  KANBAN_COLUMNS.forEach((col) => { col.label = t(`col.${col.key}`); });
}

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
  return new Intl.DateTimeFormat(state.lang === 'zh' ? 'zh-CN' : 'en-US', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(value));
}

function roleLabel(kind) {
  return t(`role.${kind}`) !== `role.${kind}` ? t(`role.${kind}`) : kind;
}

function statusLabel(status) {
  return t(`status.${status}`) !== `status.${status}` ? t(`status.${status}`) : status;
}

function updateMetrics() {
  const counts = Object.fromEntries(['queued', 'starting', 'running', 'awaiting_approval', 'completed', 'failed', 'blocked', 'cancelled', 'orphaned'].map((key) => [key, state.tasks.filter((task) => task.status === key).length]));
  const active = counts.running + counts.starting;
  const finished = counts.completed + counts.failed + counts.blocked + counts.cancelled + counts.orphaned;
  $('#metric-total').textContent = state.tasks.length;
  $('#metric-active').textContent = active;
  $('#metric-approval').textContent = counts.awaiting_approval;
  $('#metric-rate').textContent = finished ? `${Math.round(counts.completed / finished * 100)}%` : '—';
  $('#metric-capacity').textContent = state.lang === 'zh' ? `并发上限 ${state.doctor?.max_concurrency ?? 2}` : `Concurrency limit ${state.doctor?.max_concurrency ?? 2}`;
  $('#nav-all').textContent = state.tasks.length;
  $('#nav-running').textContent = active;
  $('#nav-queued').textContent = counts.queued;
  $('#nav-approval').textContent = counts.awaiting_approval;
  $('#nav-completed').textContent = counts.completed;
  $('#nav-failed').textContent = counts.failed + counts.blocked + counts.orphaned;
}

function updateCacheMetrics() {
  const cache = state.cache;
  const warm = cache?.warm;
  const rate = cache?.target?.verified_warm_hit_rate;
  $('#metric-cache').textContent = rate == null ? '—' : `${(rate * 100).toFixed(1)}%`;
  $('#metric-cache-detail').textContent = warm ? t('cache.warmSamples', { n: warm.samples, v: warm.verified_samples }) : t('cache.insufficient');
  const status = cache?.target?.status || 'insufficient_samples';
  const targetRate = cache?.target?.hit_rate;
  const labels = { achieved: t('cache.achieved', { r: targetRate == null ? '' : `${(targetRate * 100).toFixed(0)}% ` }), below_target: t('cache.below'), insufficient_samples: t('cache.insufficient'), unverified_route: t('cache.unverified') };
  const target = $('#cache-target');
  target.className = `health-chip ${status === 'achieved' ? 'ok' : (status === 'below_target' ? 'bad' : '')}`;
  target.lastChild.textContent = labels[status] || status;
  const cohorts = cache?.cohorts || [];
  $('#cache-cohort-body').innerHTML = cohorts.map((item) => `
    <tr>
      <td class="task-name"><strong>${escapeHtml((item.cache_cohort || 'unknown').slice(-12))}</strong><small>${escapeHtml((item.cache_cohort_sha256 || '').slice(0, 12))}</small></td>
      <td class="model-cell"><span>${escapeHtml(item.gateway || 'unknown')}</span><small>${escapeHtml(item.model || 'unknown')}</small></td>
      <td><span class="status ${item.cohort_class === 'warm' ? 'completed' : 'queued'}">${escapeHtml(item.cohort_class)}</span></td>
      <td>${escapeHtml(item.samples)} · ${escapeHtml(item.verified_samples)} ${t('cache.verified')}</td>
      <td>${item.verified_cache_hit_rate == null ? t('cache.unverifiedMark') : `${(item.verified_cache_hit_rate * 100).toFixed(1)}% ${t('cache.verified')}`}</td>
    </tr>`).join('') || `<tr><td colspan="5" class="objective">${t('cache.noSamples')}</td></tr>`;
}

function renderTasks() {
  const query = state.search.toLowerCase();
  const tasks = state.tasks.filter((task) => {
    const statusMatch = !state.status || task.status === state.status || (state.status === 'running' && task.status === 'starting') || (state.status === 'failed' && ['failed', 'blocked', 'orphaned'].includes(task.status));
    const text = `${task.id} ${task.objective} ${task.profile || ''} ${task.model} ${task.upstream_model || ''} ${task.gateway || ''} ${task.kind}`.toLowerCase();
    return statusMatch && (!query || text.includes(query));
  });
  $('#empty-state').hidden = tasks.length > 0;
  applyViewVisibility(tasks.length);
  renderKanban(tasks);
  $('#task-body').innerHTML = tasks.map((task) => `
    <tr data-task-id="${escapeHtml(task.id)}">
      <td class="task-name"><strong title="${escapeHtml(task.objective)}">${escapeHtml(task.objective)}</strong><small>${escapeHtml(task.id)}</small></td>
      <td class="model-cell"><span>${escapeHtml(task.profile || roleLabel(task.kind))}</span><small>${escapeHtml(task.model)} · ${escapeHtml(task.gateway || 'legacy')}</small></td>
      <td><span class="status ${escapeHtml(task.status)}">${escapeHtml(statusLabel(task.status))}</span></td>
      <td>${escapeHtml(formatTime(task.created_at))}</td>
      <td><button class="row-action" data-open-task="${escapeHtml(task.id)}">${t('action.view')}</button></td>
    </tr>`).join('');
}

const KANBAN_COLUMNS = [
  { key: 'queued', label: '', match: ['queued'] },
  { key: 'running', label: '', match: ['running', 'starting'] },
  { key: 'awaiting_approval', label: '', match: ['awaiting_approval'] },
  { key: 'completed', label: '', match: ['completed'] },
  { key: 'failed', label: '', match: ['failed', 'blocked', 'orphaned', 'cancelled'] },
];

function applyViewVisibility(count) {
  const board = state.view === 'board';
  $('#kanban-board').hidden = !board;
  $('.task-panel .table-wrap').style.display = board ? 'none' : '';
  $('#empty-state').hidden = count > 0;
  $$('.view-btn').forEach((btn) => btn.classList.toggle('active', btn.dataset.view === state.view));
}

function renderKanban(tasks) {
  const board = $('#kanban-board');
  board.innerHTML = KANBAN_COLUMNS.map((col) => {
    const items = tasks.filter((task) => col.match.includes(task.status));
    const cards = items.map((task) => `
      <article class="kanban-card" data-open-task="${escapeHtml(task.id)}" tabindex="0" role="button" title="${escapeHtml(task.objective)}">
        <div class="kanban-agent"><span class="kanban-avatar ${escapeHtml(task.kind)}">${escapeHtml((task.profile || roleLabel(task.kind)).slice(0, 1).toUpperCase())}</span><div class="kanban-who"><strong>${escapeHtml(task.profile || roleLabel(task.kind))}</strong><small>${escapeHtml(task.model)} · ${escapeHtml(task.gateway || 'legacy')}</small></div></div>
        <p class="kanban-objective">${escapeHtml(task.objective)}</p>
        <div class="kanban-foot"><span class="status ${escapeHtml(task.status)}">${escapeHtml(statusLabel(task.status))}</span><time>${escapeHtml(formatTime(task.created_at))}</time></div>
      </article>`).join('');
    return `
      <section class="kanban-col kanban-${col.key}">
        <header class="kanban-col-head"><span>${escapeHtml(col.label)}</span><b>${items.length}</b></header>
        <div class="kanban-cards">${cards || `<div class="kanban-empty">${t('kanban.empty')}</div>`}</div>
      </section>`;
  }).join('');
}

function populateModels() {
  const models = state.doctor?.allowed_models || [];
  const routes = Object.fromEntries((state.doctor?.model_routes || []).map((item) => [item.model, item]));
  for (const id of ['orchestrate-model', 'single-model']) {
    const select = $(`#${id}`);
    const previous = select.value;
    const automatic = `<option value="">${t('opt.autoRoute')}</option>`;
    select.innerHTML = automatic + models.map((model) => {
      const route = routes[model];
      const availability = route && route.routable === false ? t('opt.notRoutable') : '';
      const suffix = route ? ` · ${route.provider || route.primary}${route.billing_class ? ` · ${route.billing_class}` : ''}${availability}` : '';
      return `<option value="${escapeHtml(model)}">${escapeHtml(model + suffix)}</option>`;
    }).join('');
    select.value = models.includes(previous) || previous === '' ? previous : '';
  }
}

function populateProfiles() {
  const profiles = state.doctor?.worker_profiles || [];
  for (const [id, preferred] of [['orchestrate-profile', ''], ['single-profile', '']]) {
    const select = $(`#${id}`);
    const previous = select.value;
    select.innerHTML = `<option value="">${t('opt.noProfile')}</option>` + profiles.map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)} · ${escapeHtml(item.model)} · ${escapeHtml(item.reasoning_effort)}</option>`).join('');
    select.value = profiles.some((item) => item.name === previous) ? previous : preferred;
  }
}

function populateGateways() {
  const gateways = (state.doctor?.gateways || []).filter((item) => item.enabled);
  for (const id of ['orchestrate-gateway', 'single-gateway']) {
    const select = $(`#${id}`);
    const previous = select.value;
    select.innerHTML = `<option value="">${t('opt.autoGateway')}</option>` + gateways.map((item) => {
      const protocol = item.response_mode === 'native' ? t('protocol.native') : t('protocol.translated');
      const capabilities = (item.capabilities || []).join(', ');
      return `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)} · ${protocol}${capabilities ? ` · ${capabilities}` : ''}</option>`;
    }).join('');
    select.value = gateways.some((item) => item.name === previous) ? previous : '';
  }
}

function updateHealth() {
  const node = $('#proxy-health');
  const gateways = state.doctor?.gateways || [];
  const defaultGateway = gateways.find((item) => item.default);
  const gwOk = (g) => Boolean(g && g.enabled && g.api_reachable && g.credential_configured);
  const healthy = Boolean(state.doctor?.codex_path && (!defaultGateway || gwOk(defaultGateway)));
  const scheduler = state.doctor?.scheduler_role === 'active' ? t('health.schedulerActive') : t('health.schedulerIdle');
  node.className = `health-chip ${healthy ? 'ok' : 'bad'}`;
  node.lastChild.textContent = healthy ? t('health.online', { s: scheduler }) : t('health.offline');
  for (const name of ['opencodex', 'cliproxyapi']) {
    const g = gateways.find((item) => item.name === name);
    const chip = $(`#gw-${name}`);
    const metric = $(`#gw-metric-${name}`);
    if (!chip) continue;
    if (!g) {
      chip.className = 'health-chip gw-chip'; chip.querySelector('span').textContent = name; chip.title = t('gw.absent');
      if (metric) { metric.className = 'gw-item'; metric.querySelector('em').textContent = t('gw.absent'); metric.title = t('gw.absent'); }
      continue;
    }
    const ok = gwOk(g);
    chip.className = `health-chip gw-chip ${ok ? 'ok' : 'bad'}`;
    const label = g.name === 'opencodex' ? 'OpenCodex' : 'CLIProxyAPI';
    chip.querySelector('span').textContent = `${label} ${ok ? '✓' : '✗'}`;
    chip.title = `${label}: ${ok ? t('gw.connected') : t('gw.disconnected')} · ${g.response_mode || ''}${g.default ? ' · default' : ''}`;
    if (metric) {
      metric.className = `gw-item ${ok ? 'ok' : 'bad'}`;
      metric.querySelector('em').textContent = ok ? t('gw.online') : t('gw.offline');
      metric.title = `${label}: ${ok ? t('gw.connected') : t('gw.disconnected')} · ${g.response_mode || ''}${g.default ? ' · default' : ''}`;
    }
  }
  const anyGateway = gateways.some((g) => gwOk(g));
  const canDelegate = Boolean(state.doctor?.codex_path) && anyGateway;
  const newBtn = $('#new-task-button');
  if (newBtn) {
    newBtn.disabled = !canDelegate;
    newBtn.title = canDelegate ? '' : t('gw.needGateway');
  }
}

async function refresh(silent = false) {
  try {
    const [doctor, tasks, cache] = await Promise.all([api('/api/doctor'), api('/api/tasks?limit=500'), api('/api/cache-metrics?model=deepseek%2Fdeepseek-v4-flash')]);
    state.doctor = doctor;
    state.tasks = tasks.tasks;
    state.cache = cache;
    updateMetrics();
    updateCacheMetrics();
    renderTasks();
    updateHealth();
    populateModels();
    populateProfiles();
    populateGateways();
    if (state.selected) await loadTask(state.selected, true);
    if (!silent) toast(t('toast.refreshed'));
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
    $('#detail-kind').textContent = task.profile || roleLabel(task.kind);
    $('#detail-title').textContent = task.name || task.id;
    $('#detail-objective').textContent = task.objective;
    const protocol = task.response_mode === 'native' ? t('protocol.native') : (task.response_mode === 'translated' ? t('protocol.translated') : null);
    $('#detail-meta').innerHTML = [statusLabel(task.status), task.profile && `Profile ${task.profile}`, `${t('meta.model')} ${task.model}`, task.provider && `${t('meta.provider')} ${task.provider}`, task.upstream_model && `${t('meta.upstream')} ${task.upstream_model}`, task.gateway && `${t('meta.gateway')} ${task.gateway}`, task.execution_channel && `${t('meta.channel')} ${task.execution_channel}`, protocol, task.route_audit && `${t('meta.verified')} ${task.route_audit.verification}`, task.fallback_gateway && `${t('meta.fallback')} ${task.fallback_gateway}`, task.sandbox, formatTime(task.created_at), task.worktree_path].filter(Boolean).map((value) => `<span>${escapeHtml(value)}</span>`).join('');
    const actions = [];
    if (task.status === 'awaiting_approval') actions.push(`<button class="button approve" data-approve="${escapeHtml(task.id)}" data-approval-id="${escapeHtml(task.approval_id || '')}" data-scope-digest="${escapeHtml(task.approval_scope_digest || '')}">${t('action.approve')}</button>`);
    if (!['completed', 'failed', 'cancelled', 'blocked', 'orphaned'].includes(task.status)) actions.push(`<button class="button danger" data-cancel="${escapeHtml(task.id)}">${t('action.cancel')}</button>`);
    if (['failed', 'blocked'].includes(task.status) && task.fallback_gateway && ['plan', 'explore', 'review'].includes(task.kind)) actions.push(`<button class="button" data-fallback="${escapeHtml(task.id)}">${escapeHtml(t('action.fallback', { gw: task.fallback_gateway }))}</button>`);
    if ((['failed', 'blocked'].includes(task.status) || task.schema?.valid === false) && ['explore', 'review'].includes(task.kind)) actions.push(`<button class="button" data-escalate="${escapeHtml(task.id)}">${t('action.escalate')}</button>`);
    $('#detail-actions').innerHTML = actions.join('');
    $('#detail-route').textContent = task.route_audit ? JSON.stringify(task.route_audit, null, 2) : t('detail.noRoute');
    $('#detail-governance').textContent = JSON.stringify({ approval: task.approval_scope || null, approval_scope_digest: task.approval_scope_digest || null, budget: task.budget || null, schema: task.schema || null, cache: task.cache_audit || null }, null, 2);
    $('#detail-result').textContent = task.result ? JSON.stringify(task.result, null, 2) : (task.error || t('detail.waitingWorker'));
    $('#detail-events').innerHTML = events.events.slice().reverse().map((event) => `<div class="event"><strong>${escapeHtml(event.event_type)}</strong><small>${escapeHtml(formatTime(event.created_at))}</small></div>`).join('') || `<p class="objective">${t('detail.noEvents')}</p>`;
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
    profile: $('#orchestrate-profile').value || null,
    max_tasks: Number($('#orchestrate-max').value),
    gateway: $('#orchestrate-gateway').value || null,
    context_pack: $('#orchestrate-context-pack').value || null,
  };
  if (!payload.objective || !payload.workspace) return toast(t('toast.needObjective'), true);
  try {
    const result = await api('/api/orchestrate', { method: 'POST', body: JSON.stringify(payload) });
    $('#task-dialog').close();
    toast(t('toast.orchQueued', { id: result.root_task_id }));
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
    profile: $('#single-profile').value || null,
    model: $('#single-model').value,
    gateway: $('#single-gateway').value || null,
    execution_channel: $('#single-channel').value,
    required_capabilities: $('#single-capabilities').value.split(',').map((value) => value.trim()).filter(Boolean),
    reasoning_effort: $('#single-effort').value || null,
    mode: $('#single-mode').value,
    timeout_seconds: Number($('#single-timeout').value),
    success_criteria: success ? [success] : [],
    context_pack: $('#single-context-pack').value || null,
  };
  if (!payload.objective || !payload.workspace) return toast(t('toast.needObjective'), true);
  try {
    const result = await api('/api/tasks', { method: 'POST', body: JSON.stringify(payload) });
    $('#task-dialog').close();
    toast(t('toast.workerQueued', { id: result.task_id }));
    await refresh(true);
    await loadTask(result.task_id);
  } catch (error) { toast(error.message, true); }
}

document.addEventListener('click', async (event) => {
  const open = event.target.closest('[data-open-task]');
  if (open) return loadTask(open.dataset.openTask);
  const approve = event.target.closest('[data-approve]');
  if (approve) {
    const body = { approval_id: approve.dataset.approvalId || null, scope_digest: approve.dataset.scopeDigest || null };
    try { await api(`/api/tasks/${encodeURIComponent(approve.dataset.approve)}/approve`, { method: 'POST', body: JSON.stringify(body) }); toast(t('toast.approved')); await refresh(true); } catch (error) { toast(error.message, true); }
  }
  const cancel = event.target.closest('[data-cancel]');
  if (cancel && confirm(t('confirm.cancel'))) {
    try { await api(`/api/tasks/${encodeURIComponent(cancel.dataset.cancel)}/cancel`, { method: 'POST', body: '{}' }); toast(t('toast.cancelSent')); await refresh(true); } catch (error) { toast(error.message, true); }
  }
  const fallback = event.target.closest('[data-fallback]');
  if (fallback && confirm(t('confirm.fallback'))) {
    try { const result = await api(`/api/tasks/${encodeURIComponent(fallback.dataset.fallback)}/retry-fallback`, { method: 'POST', body: '{}' }); toast(t('toast.fallbackQueued', { id: result.task_id })); await refresh(true); await loadTask(result.task_id); } catch (error) { toast(error.message, true); }
  }
  const escalate = event.target.closest('[data-escalate]');
  if (escalate && confirm(t('confirm.escalate'))) {
    try { const result = await api(`/api/tasks/${encodeURIComponent(escalate.dataset.escalate)}/escalate`, { method: 'POST', body: '{}' }); toast(t('toast.escalateQueued', { id: result.task_id })); await refresh(true); await loadTask(result.task_id); } catch (error) { toast(error.message, true); }
  }
});

$$('.nav-item').forEach((button) => button.addEventListener('click', () => {
  $$('.nav-item').forEach((item) => item.classList.remove('active'));
  button.classList.add('active');
  state.status = button.dataset.status;
  renderTasks();
}));
$$('.view-btn').forEach((button) => button.addEventListener('click', () => {
  state.view = button.dataset.view;
  localStorage.setItem('lw-view', state.view);
  renderTasks();
}));
function setLanguage(lang) {
  state.lang = lang;
  localStorage.setItem('lw-lang', lang);
  applyI18n();
  updateMetrics();
  updateCacheMetrics();
  renderTasks();
  updateHealth();
  populateModels();
  populateProfiles();
  populateGateways();
  if (state.selected) loadTask(state.selected, true);
  toast(t('lang.switched'));
}
$$('.lang-btn').forEach((button) => button.addEventListener('click', () => setLanguage(button.dataset.lang)));
$$('.tab').forEach((button) => button.addEventListener('click', () => {
  $$('.tab').forEach((item) => item.classList.toggle('active', item === button));
  $$('.tab-pane').forEach((pane) => pane.classList.toggle('active', pane.id === `pane-${button.dataset.tab}`));
}));
$('#search-input').addEventListener('input', (event) => { state.search = event.target.value; renderTasks(); });
$('#new-task-button').addEventListener('click', () => $('#task-dialog').showModal());
$('#refresh-button').addEventListener('click', () => refresh());
$('#purge-button').addEventListener('click', async () => {
  if (!confirm(t('confirm.purge'))) return;
  try {
    const result = await api('/api/tasks/purge', { method: 'POST', body: '{}' });
    toast(t('toast.purged', { n: result.deleted }));
    if (state.selected) closeDrawer();
    await refresh(true);
  } catch (error) { toast(error.message, true); }
});
$('#submit-orchestrate').addEventListener('click', submitOrchestration);
$('#submit-single').addEventListener('click', submitSingle);
$('#close-task-dialog').addEventListener('click', () => $('#task-dialog').close());
$('#close-drawer').addEventListener('click', closeDrawer);
$('#drawer-backdrop').addEventListener('click', closeDrawer);
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeDrawer(); });

applyI18n();
refresh(true);
setInterval(() => { if (!document.hidden) refresh(true); }, 3000);
