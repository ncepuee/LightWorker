/* LightWorker 0.5.0 — Mission Control console */
const token = document.querySelector('meta[name="lightworker-token"]').content;
const state = {
  lang: localStorage.getItem('lw-lang') || 'zh',
  view: 'overview', tasks: [], doctor: null, cache: null,
  status: '', search: '', boardList: localStorage.getItem('lw-view') || 'board',
  selected: null, drawerTab: 'overview', lastSync: null, paletteIndex: 0, paletteItems: [],
};
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

/* ================= i18n ================= */
const I18N = {
  zh: {
    'brand.sub': 'Agent Control Plane',
    'nav.overview': '概览', 'nav.tasks': '任务', 'nav.system': '系统',
    'note.eyebrow': '安全模式', 'note.body': '写任务进入独立 worktree，并在 auto_readonly 下等待审批。',
    'health.schedulerActive': '调度运行中', 'health.schedulerIdle': '调度待命', 'top.waiting': '等待同步…',
    'top.refresh': '刷新', 'top.purge': '清空历史', 'top.new': '新建任务', 'top.palette': '命令面板 (Ctrl+K)',
    'view.overview': '概览', 'view.tasks': '任务', 'view.cachelab': 'Cache Lab', 'view.system': '系统',
    'viewSub.overview': '任务、网关与缓存的实时状态', 'viewSub.tasks': '看板与列表双视图，3 秒自动刷新',
    'viewSub.cachelab': 'DeepSeek 暖缓存命中率与 Cohort 明细', 'viewSub.system': '网关、模型路由与 Worker Profile 配置',
    'common.close': '关闭', 'common.details': '详情 →', 'common.allTasks': '全部任务 →', 'common.view': '查看',
    'metrics.total': '任务总数', 'metrics.totalSub': '当前状态库', 'metrics.active': '活跃 Worker',
    'metrics.approval': '待审批', 'metrics.approvalSub': '写入前人工确认', 'metrics.rate': '完成率',
    'metrics.rateSub': '排除排队任务', 'metrics.cache': '暖缓存命中率', 'metrics.capacity': '并发上限 {n}',
    'overview.gateways': '网关健康', 'overview.cache': '缓存 Cohort 目标', 'overview.approvals': '审批收件箱',
    'overview.recent': '最近任务', 'overview.noApprovals': '没有待审批的写任务', 'overview.noRecent': '还没有任务',
    'overview.noGateway': '未配置网关',
    'board.search': '搜索目标、模型或任务 ID', 'board.board': '看板', 'board.list': '列表',
    'board.viewBoard': '看板视图', 'board.viewList': '列表视图',
    'board.colTask': '任务', 'board.colRole': '角色 / 模型', 'board.colStatus': '状态', 'board.colTime': '创建时间', 'board.colAction': '操作',
    'board.empty': '暂时没有任务', 'board.emptySub': '创建一个自动规划目标，或提交单个只读 Worker。', 'kanban.empty': '暂无任务',
    'col.queued': '等待调度', 'col.running': '进行中', 'col.awaiting_approval': '待审批', 'col.completed': '已完成', 'col.failed': '异常',
    'filter.all': '全部', 'filter.failed': '异常',
    'status.queued': '等待调度', 'status.starting': '正在启动', 'status.running': '正在运行', 'status.awaiting_approval': '需要审批',
    'status.completed': '已完成', 'status.failed': '失败', 'status.cancelled': '已取消', 'status.blocked': '已阻塞', 'status.orphaned': '已孤立',
    'role.plan': 'Planner', 'role.explore': 'Explorer', 'role.execute': 'Executor', 'role.review': 'Reviewer',
    'cache.targetTitle': '目标 Cohort 状态', 'cache.title': '缓存 Cohort 明细', 'cache.colPath': '网关 / 模型', 'cache.colStatus': '状态', 'cache.colSamples': '样本', 'cache.colHit': '命中率',
    'cache.noSamples': '尚无可用缓存样本', 'cache.insufficient': '样本不足', 'cache.warm': '暖', 'cache.cold': '冷',
    'cache.verified': '已核验', 'cache.unverifiedMark': '—（未核验）', 'cache.warmSamples': '{n} 个暖样本 · {v} 已核验',
    'cache.achieved': '已达到 {r} 目标', 'cache.below': '尚未达到目标', 'cache.unverified': '路由未核验',
    'cache.ofTarget': '目标 {r} · 最少 {n} 个暖样本', 'cache.cohortOf': 'Cohort {c}',
    'sys.runtime': '运行时', 'sys.budget': '预算与缓存配置', 'sys.gateways': '网关', 'sys.models': '模型路由', 'sys.profiles': 'Worker Profile',
    'sys.colName': '名称', 'sys.colProto': '协议', 'sys.colCaps': '能力', 'sys.colCred': '凭据', 'sys.colReach': '连接',
    'sys.colModel': '模型', 'sys.colProvider': '提供方', 'sys.colBilling': '计费', 'sys.colPrimary': '主网关', 'sys.colFallback': '备用', 'sys.colRoutable': '可路由',
    'sys.colProfile': 'Profile', 'sys.colDesc': '用途', 'sys.colEffort': '强度', 'sys.colGateway': '网关',
    'sys.home': '状态目录', 'sys.database': '状态库', 'sys.codex': 'Codex CLI', 'sys.scheduler': '调度器',
    'sys.concurrency': '全局并发', 'sys.isolated': '隔离用户配置', 'sys.catalog': '模型目录',
    'sys.maxSub': '单根并发', 'sys.maxAttempts': '尝试上限', 'sys.maxRetries': '备用重试', 'sys.maxEscalations': '深度升级',
    'sys.cacheAffinity': '缓存亲和', 'sys.cacheWindow': '亲和窗口', 'sys.cacheWarm': '暖样本窗口', 'sys.cacheTarget': '目标命中率', 'sys.cacheMin': '最少暖样本',
    'sys.yes': '已配置', 'sys.no': '未配置', 'sys.active': 'active', 'sys.standby': 'standby', 'sys.none': '—',
    'dlg.title': '创建协作任务', 'dlg.tabOrch': '自动规划', 'dlg.tabSingle': '单个 Worker', 'dlg.objective': '目标',
    'dlg.objectivePh': '例如：检查登录模块的可靠性，拆成并行只读调查并汇总证据。', 'dlg.workspace': '工作区', 'dlg.mode': '执行模式',
    'dlg.modeAutoReadonly': 'auto_readonly（推荐）', 'dlg.plannerModel': 'Planner 模型', 'dlg.plannerProfile': 'Planner Profile',
    'dlg.gateway': '网关', 'dlg.maxSub': '最大子任务', 'dlg.contextPack': '共享 Context Pack（可选，最多 32KiB）',
    'dlg.contextPackPh': '仅填写多次任务都需要的稳定、已审阅上下文；不要填密钥或动态日志。', 'dlg.submitOrch': '生成任务 DAG',
    'dlg.singleObjective': '任务目标', 'dlg.singleObjectivePh': '给 Worker 一个边界清楚、可验证的目标。', 'dlg.kind': '角色',
    'dlg.workerProfile': 'Worker Profile', 'dlg.model': '模型', 'dlg.channel': '执行通道', 'dlg.channelNative': 'OpenCodex 原生子代理',
    'dlg.capabilities': '所需能力', 'dlg.capabilitiesPh': '例如：web_search', 'dlg.effort': '推理强度', 'dlg.effortAuto': '按 Profile / 自动路由',
    'dlg.timeout': '超时（秒）', 'dlg.success': '成功条件', 'dlg.successPh': '例如：列出文件证据并给出可复现命令',
    'dlg.contextPackPh2': '相同 Cohort 的 Worker 使用完全相同的稳定上下文。', 'dlg.submitSingle': '提交 Worker',
    'detail.title': '任务详情', 'detail.tabOverview': '概览', 'detail.tabResult': '结果', 'detail.tabGovernance': '治理', 'detail.tabEvents': '时间线',
    'detail.objective': '目标', 'detail.route': '路由审计', 'detail.governance': '预算与 Schema', 'detail.result': '结构化结果', 'detail.events': '事件时间线',
    'detail.waitingRoute': '等待调度…', 'detail.noRoute': '旧任务没有路由审计数据', 'detail.waitingWorker': '等待 Worker 返回…', 'detail.noEvents': '暂无事件',
    'meta.model': '模型', 'meta.provider': '提供方', 'meta.upstream': '上游', 'meta.gateway': '网关', 'meta.channel': '通道',
    'meta.verified': '核验', 'meta.fallback': '备用', 'meta.profile': 'Profile',
    'action.approve': '批准当前权限范围', 'action.cancel': '取消任务', 'action.fallback': '改用 {gw} 重试', 'action.escalate': '升级到深度 Worker',
    'gw.connected': '已连接', 'gw.disconnected': '未连接', 'gw.absent': '未配置', 'gw.online': '在线', 'gw.offline': '离线',
    'gw.needGateway': '至少一个网关连接成功才能委派任务', 'protocol.native': 'Native Responses', 'protocol.translated': 'Responses → Chat 转译',
    'opt.autoRoute': '按 Profile / 自动路由', 'opt.noProfile': '不指定 Profile', 'opt.autoGateway': '按模型自动选择（推荐）', 'opt.notRoutable': ' · 当前不可路由',
    'palette.ph': '搜索任务或命令…', 'palette.actions': '命令', 'palette.tasks': '任务', 'palette.noResult': '没有匹配的结果', 'palette.newTask': '新建任务', 'palette.goto': '跳转到{view}',
    'toast.refreshed': '任务状态已刷新', 'toast.needObjective': '请填写目标和工作区', 'toast.orchQueued': '规划任务已入队：{id}',
    'toast.workerQueued': 'Worker 已入队：{id}', 'toast.approved': '当前权限范围已批准', 'toast.cancelSent': '已发送取消请求',
    'toast.fallbackQueued': '备用任务已入队：{id}', 'toast.escalateQueued': '升级任务已入队：{id}', 'toast.purged': '已清空 {n} 条历史任务',
    'toast.langZh': '已切换为中文', 'toast.langEn': 'Switched to English',
    'confirm.cancel': '确定取消这个任务吗？',
    'confirm.fallback': '创建一个新的只读任务并改用备用网关？原任务会保留。',
    'confirm.escalate': '创建一个新的只读深度 Worker 尝试？原任务和原始结果会保留。',
    'confirm.purge': '确定清空所有已结束的历史任务吗？\n\n将删除：已完成、失败、已阻塞、已孤立、已取消的任务及其事件与用量记录。\n排队中、运行中、待审批的任务不会被删除。此操作不可恢复。',
    'rel.now': '刚刚', 'rel.s': '{n} 秒前', 'rel.m': '{n} 分钟前', 'rel.h': '{n} 小时前', 'rel.d': '{n} 天前',
  },
  en: {
    'brand.sub': 'Agent Control Plane',
    'nav.overview': 'Overview', 'nav.tasks': 'Tasks', 'nav.system': 'System',
    'note.eyebrow': 'Safe Mode', 'note.body': 'Write tasks run in an isolated worktree and await approval under auto_readonly.',
    'health.schedulerActive': 'scheduler active', 'health.schedulerIdle': 'scheduler idle', 'top.waiting': 'waiting to sync…',
    'top.refresh': 'Refresh', 'top.purge': 'Clear History', 'top.new': 'New Task', 'top.palette': 'Command palette (Ctrl+K)',
    'view.overview': 'Overview', 'view.tasks': 'Tasks', 'view.cachelab': 'Cache Lab', 'view.system': 'System',
    'viewSub.overview': 'Live status of tasks, gateways and cache', 'viewSub.tasks': 'Board and list views, 3s auto refresh',
    'viewSub.cachelab': 'DeepSeek warm-cache hit rate and cohort details', 'viewSub.system': 'Gateways, model routes and worker profiles',
    'common.close': 'Close', 'common.details': 'Details →', 'common.allTasks': 'All tasks →', 'common.view': 'View',
    'metrics.total': 'Total Tasks', 'metrics.totalSub': 'Current state store', 'metrics.active': 'Active Workers',
    'metrics.approval': 'Pending Approval', 'metrics.approvalSub': 'Manual confirm before write', 'metrics.rate': 'Completion Rate',
    'metrics.rateSub': 'Excludes queued tasks', 'metrics.cache': 'Warm Cache Hit Rate', 'metrics.capacity': 'Concurrency limit {n}',
    'overview.gateways': 'Gateway Health', 'overview.cache': 'Cache Cohort Target', 'overview.approvals': 'Approval Inbox',
    'overview.recent': 'Recent Tasks', 'overview.noApprovals': 'No write tasks awaiting approval', 'overview.noRecent': 'No tasks yet',
    'overview.noGateway': 'No gateway configured',
    'board.search': 'Search objective, model or task ID', 'board.board': 'Board', 'board.list': 'List',
    'board.viewBoard': 'Board view', 'board.viewList': 'List view',
    'board.colTask': 'Task', 'board.colRole': 'Role / Model', 'board.colStatus': 'Status', 'board.colTime': 'Created', 'board.colAction': 'Actions',
    'board.empty': 'No tasks yet', 'board.emptySub': 'Create an auto-planned objective, or submit a single read-only worker.', 'kanban.empty': 'No tasks',
    'col.queued': 'Queued', 'col.running': 'Running', 'col.awaiting_approval': 'Approval', 'col.completed': 'Done', 'col.failed': 'Failed',
    'filter.all': 'All', 'filter.failed': 'Failed',
    'status.queued': 'Queued', 'status.starting': 'Starting', 'status.running': 'Running', 'status.awaiting_approval': 'Needs Approval',
    'status.completed': 'Completed', 'status.failed': 'Failed', 'status.cancelled': 'Cancelled', 'status.blocked': 'Blocked', 'status.orphaned': 'Orphaned',
    'role.plan': 'Planner', 'role.explore': 'Explorer', 'role.execute': 'Executor', 'role.review': 'Reviewer',
    'cache.targetTitle': 'Target cohort status', 'cache.title': 'Cache cohort details', 'cache.colPath': 'Gateway / Model', 'cache.colStatus': 'Status', 'cache.colSamples': 'Samples', 'cache.colHit': 'Hit Rate',
    'cache.noSamples': 'No cache samples available', 'cache.insufficient': 'Insufficient samples', 'cache.warm': 'warm', 'cache.cold': 'cold',
    'cache.verified': 'verified', 'cache.unverifiedMark': '— (unverified)', 'cache.warmSamples': '{n} warm samples · {v} verified',
    'cache.achieved': 'Reached {r} target', 'cache.below': 'Below target', 'cache.unverified': 'Route unverified',
    'cache.ofTarget': 'Target {r} · min {n} warm samples', 'cache.cohortOf': 'Cohort {c}',
    'sys.runtime': 'Runtime', 'sys.budget': 'Budget & Cache Config', 'sys.gateways': 'Gateways', 'sys.models': 'Model Routes', 'sys.profiles': 'Worker Profiles',
    'sys.colName': 'Name', 'sys.colProto': 'Protocol', 'sys.colCaps': 'Capabilities', 'sys.colCred': 'Credential', 'sys.colReach': 'Reachability',
    'sys.colModel': 'Model', 'sys.colProvider': 'Provider', 'sys.colBilling': 'Billing', 'sys.colPrimary': 'Primary', 'sys.colFallback': 'Fallback', 'sys.colRoutable': 'Routable',
    'sys.colProfile': 'Profile', 'sys.colDesc': 'Purpose', 'sys.colEffort': 'Effort', 'sys.colGateway': 'Gateway',
    'sys.home': 'State home', 'sys.database': 'State store', 'sys.codex': 'Codex CLI', 'sys.scheduler': 'Scheduler',
    'sys.concurrency': 'Global concurrency', 'sys.isolated': 'Isolated user config', 'sys.catalog': 'Model catalog',
    'sys.maxSub': 'Root concurrency', 'sys.maxAttempts': 'Max attempts', 'sys.maxRetries': 'Fallback retries', 'sys.maxEscalations': 'Escalations',
    'sys.cacheAffinity': 'Cache affinity', 'sys.cacheWindow': 'Affinity window', 'sys.cacheWarm': 'Warm window', 'sys.cacheTarget': 'Target rate', 'sys.cacheMin': 'Min warm samples',
    'sys.yes': 'Configured', 'sys.no': 'Missing', 'sys.active': 'active', 'sys.standby': 'standby', 'sys.none': '—',
    'dlg.title': 'Create Collaboration Task', 'dlg.tabOrch': 'Auto Plan', 'dlg.tabSingle': 'Single Worker', 'dlg.objective': 'Objective',
    'dlg.objectivePh': 'e.g. Review the login module reliability, split into parallel read-only investigations and summarize evidence.',
    'dlg.workspace': 'Workspace', 'dlg.mode': 'Mode', 'dlg.modeAutoReadonly': 'auto_readonly (recommended)',
    'dlg.plannerModel': 'Planner Model', 'dlg.plannerProfile': 'Planner Profile', 'dlg.gateway': 'Gateway', 'dlg.maxSub': 'Max Subtasks',
    'dlg.contextPack': 'Shared Context Pack (optional, up to 32KiB)',
    'dlg.contextPackPh': 'Only stable, reviewed context reused across tasks; do not include secrets or dynamic logs.', 'dlg.submitOrch': 'Generate Task DAG',
    'dlg.singleObjective': 'Task Objective', 'dlg.singleObjectivePh': 'Give the worker a well-bounded, verifiable objective.', 'dlg.kind': 'Role',
    'dlg.workerProfile': 'Worker Profile', 'dlg.model': 'Model', 'dlg.channel': 'Execution Channel', 'dlg.channelNative': 'OpenCodex native subagent',
    'dlg.capabilities': 'Required Capabilities', 'dlg.capabilitiesPh': 'e.g. web_search', 'dlg.effort': 'Reasoning Effort', 'dlg.effortAuto': 'By Profile / auto route',
    'dlg.timeout': 'Timeout (s)', 'dlg.success': 'Success Criteria', 'dlg.successPh': 'e.g. List file evidence and give a reproducible command',
    'dlg.contextPackPh2': 'Workers in the same cohort use identical stable context.', 'dlg.submitSingle': 'Submit Worker',
    'detail.title': 'Task Details', 'detail.tabOverview': 'Overview', 'detail.tabResult': 'Result', 'detail.tabGovernance': 'Governance', 'detail.tabEvents': 'Timeline',
    'detail.objective': 'Objective', 'detail.route': 'Route Audit', 'detail.governance': 'Budget & Schema', 'detail.result': 'Structured Result', 'detail.events': 'Event Timeline',
    'detail.waitingRoute': 'Waiting to schedule…', 'detail.noRoute': 'Legacy task has no route audit data', 'detail.waitingWorker': 'Waiting for worker to return…', 'detail.noEvents': 'No events',
    'meta.model': 'Model', 'meta.provider': 'Provider', 'meta.upstream': 'Upstream', 'meta.gateway': 'Gateway', 'meta.channel': 'Channel',
    'meta.verified': 'Verified', 'meta.fallback': 'Fallback', 'meta.profile': 'Profile',
    'action.approve': 'Approve current scope', 'action.cancel': 'Cancel task', 'action.fallback': 'Retry via {gw}', 'action.escalate': 'Escalate to deep Worker',
    'gw.connected': 'Connected', 'gw.disconnected': 'Disconnected', 'gw.absent': 'Not configured', 'gw.online': 'Online', 'gw.offline': 'Offline',
    'gw.needGateway': 'At least one gateway must be connected to delegate tasks', 'protocol.native': 'Native Responses', 'protocol.translated': 'Responses → Chat translated',
    'opt.autoRoute': 'By Profile / auto route', 'opt.noProfile': 'No profile', 'opt.autoGateway': 'Auto by model (recommended)', 'opt.notRoutable': ' · not routable',
    'palette.ph': 'Search tasks or commands…', 'palette.actions': 'Commands', 'palette.tasks': 'Tasks', 'palette.noResult': 'No matches', 'palette.newTask': 'New task', 'palette.goto': 'Go to {view}',
    'toast.refreshed': 'Task state refreshed', 'toast.needObjective': 'Please fill in objective and workspace', 'toast.orchQueued': 'Plan task queued: {id}',
    'toast.workerQueued': 'Worker queued: {id}', 'toast.approved': 'Current scope approved', 'toast.cancelSent': 'Cancel request sent',
    'toast.fallbackQueued': 'Fallback task queued: {id}', 'toast.escalateQueued': 'Escalation queued: {id}', 'toast.purged': 'Cleared {n} historical tasks',
    'toast.langZh': '已切换为中文', 'toast.langEn': 'Switched to English',
    'confirm.cancel': 'Cancel this task?',
    'confirm.fallback': 'Create a new read-only task using the fallback gateway? The original task is kept.',
    'confirm.escalate': 'Create a new read-only deep Worker attempt? Original task and result are kept.',
    'confirm.purge': 'Clear all finished historical tasks?\n\nWill delete: completed, failed, blocked, orphaned, cancelled tasks with their events and usage records.\nQueued, running and pending-approval tasks are kept. This cannot be undone.',
    'rel.now': 'just now', 'rel.s': '{n}s ago', 'rel.m': '{n}m ago', 'rel.h': '{n}h ago', 'rel.d': '{n}d ago',
  },
};
function t(key, vars) {
  let s = I18N[state.lang][key] ?? I18N.zh[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
  return s;
}
function applyI18n() {
  document.documentElement.lang = state.lang === 'zh' ? 'zh-CN' : 'en';
  $$('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $$('[data-i18n-ph]').forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  $$('[data-i18n-title]').forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  $$('[data-i18n-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
  $$('.lang-btn').forEach((btn) => btn.classList.toggle('active', btn.dataset.lang === state.lang));
  KANBAN_COLUMNS.forEach((col) => { col.label = t(col.labelKey); });
  renderViewTitle();
}

/* ================= utilities ================= */
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[c]);
}
function fmtAbs(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat(state.lang === 'zh' ? 'zh-CN' : 'en-US', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(value));
}
function relTime(value) {
  if (!value) return '—';
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 8) return t('rel.now');
  if (seconds < 60) return t('rel.s', { n: Math.floor(seconds) });
  if (seconds < 3600) return t('rel.m', { n: Math.floor(seconds / 60) });
  if (seconds < 86400) return t('rel.h', { n: Math.floor(seconds / 3600) });
  return t('rel.d', { n: Math.floor(seconds / 86400) });
}
function relKey(value) {
  const seconds = (Date.now() - new Date(value).getTime()) / 1000;
  return seconds < 60 ? 'rel.s' : seconds < 3600 ? 'rel.m' : seconds < 86400 ? 'rel.h' : 'rel.d';
}
function roleLabel(kind) { const k = `role.${kind}`; return I18N[state.lang][k] ?? kind; }
function statusLabel(status) { const k = `status.${status}`; return I18N[state.lang][k] ?? status; }
function shortId(id) { return String(id ?? '').slice(0, 10); }
function prettyJson(value, fallbackText) {
  if (value == null) return escapeHtml(fallbackText || 'null');
  const raw = JSON.stringify(value, null, 2) ?? String(fallbackText ?? '');
  return raw.replace(/("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g, (m, str, colon, bool, num) => {
    if (str) return `<span class="${colon ? 'j-key' : 'j-str'}">${escapeHtml(str)}</span>${colon || ''}`;
    if (bool) return `<span class="j-bool">${bool}</span>`;
    if (num) return `<span class="j-num">${num}</span>`;
    return escapeHtml(m);
  });
}
function toast(message, error = false) {
  const node = $('#toast');
  node.textContent = message;
  node.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.className = 'toast'; }, 3400);
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

/* ================= router ================= */
const VIEWS = {
  overview: { title: 'view.overview', sub: 'viewSub.overview' },
  tasks: { title: 'view.tasks', sub: 'viewSub.tasks' },
  cachelab: { title: 'view.cachelab', sub: 'viewSub.cachelab' },
  system: { title: 'view.system', sub: 'viewSub.system' },
};
function route() {
  const hash = location.hash.replace(/^#\/?/, '').split('?')[0];
  return VIEWS[hash] ? hash : 'overview';
}
function renderViewTitle() {
  const view = state.view;
  $('#view-title').textContent = t(VIEWS[view].title);
  $('#view-subtitle').textContent = t(VIEWS[view].sub);
}
function applyRoute() {
  state.view = route();
  $$('.view').forEach((p) => { p.hidden = p.dataset.viewPanel !== state.view; });
  $$('.nav-link').forEach((a) => a.classList.toggle('active', a.dataset.route === state.view));
  renderViewTitle();
  renderCurrentView();
}
function renderCurrentView() {
  if (state.view === 'overview') renderOverview();
  else if (state.view === 'tasks') renderTasks();
  else if (state.view === 'cachelab') renderCacheLab();
  else if (state.view === 'system') renderSystem();
}

/* ================= metrics (always-on) ================= */
function counts() {
  const c = Object.fromEntries(['queued', 'starting', 'running', 'awaiting_approval', 'completed', 'failed', 'blocked', 'cancelled', 'orphaned'].map((k) => [k, state.tasks.filter((x) => x.status === k).length]));
  c.active = c.running + c.starting;
  c.finished = c.completed + c.failed + c.blocked + c.cancelled + c.orphaned;
  c.problem = c.failed + c.blocked + c.orphaned;
  return c;
}
function updateMetrics() {
  const c = counts();
  const cap = state.doctor?.max_concurrency ?? 3;
  const cache = state.cache;
  const rate = cache?.target?.verified_warm_hit_rate;
  const setKpi = (id, value, sub, ratio) => {
    const el = $(`#${id}`);
    el.querySelector('strong').textContent = value;
    if (sub !== undefined) el.querySelector('small').textContent = sub;
    if (ratio !== undefined) el.querySelector('.kpi-bar i').style.width = `${Math.min(100, Math.max(0, ratio * 100))}%`;
  };
  setKpi('kpi-total', state.tasks.length, t('metrics.totalSub'), Math.min(1, state.tasks.length / 60));
  setKpi('kpi-active', c.active, t('metrics.capacity', { n: cap }), cap ? c.active / cap : 0);
  const approvalEl = $('#kpi-approval');
  approvalEl.classList.toggle('hot', c.awaiting_approval > 0);
  setKpi('kpi-approval', c.awaiting_approval, t('metrics.approvalSub'), c.awaiting_approval ? Math.min(1, c.awaiting_approval / 6) : 0);
  setKpi('kpi-rate', c.finished ? `${Math.round(c.completed / c.finished * 100)}%` : '—', t('metrics.rateSub'), c.finished ? c.completed / c.finished : 0);
  setKpi('kpi-cache', rate == null ? '—' : `${(rate * 100).toFixed(1)}%`, cache?.warm ? t('cache.warmSamples', { n: cache.warm.samples, v: cache.warm.verified_samples }) : t('cache.insufficient'), rate ?? 0);
  const navCount = $('#nav-task-count');
  const badge = c.awaiting_approval > 0 ? c.awaiting_approval : c.active;
  navCount.hidden = badge === 0;
  navCount.textContent = badge;
  navCount.classList.toggle('alert', c.awaiting_approval > 0);
}

/* ================= health chips ================= */
function gwOk(g) { return Boolean(g && g.enabled && g.api_reachable && g.credential_configured); }
function updateHealth() {
  const gateways = state.doctor?.gateways || [];
  for (const [mini, name, label] of [['#gw-mini-opencodex', 'opencodex', 'OpenCodex'], ['#gw-mini-cliproxyapi', 'cliproxyapi', 'CLIProxyAPI']]) {
    const el = $(mini);
    if (!el) continue;
    const g = gateways.find((item) => item.name === name);
    if (!g) { el.className = 'chip gw-mini'; el.title = `${label}: ${t('gw.absent')}`; continue; }
    const ok = gwOk(g);
    el.className = `chip gw-mini ${ok ? 'ok' : 'bad'}`;
    el.title = `${label}: ${ok ? t('gw.connected') : t('gw.disconnected')} · ${g.response_mode || ''}`;
  }
  const schedulerCard = $('#scheduler-card');
  const active = state.doctor?.scheduler_role === 'active';
  schedulerCard.classList.toggle('is-active', active);
  $('#scheduler-role').textContent = active ? t('health.schedulerActive') : t('health.schedulerIdle');
  $('#scheduler-sync').textContent = state.lastSync ? `${t('top.refresh')} · ${relTime(state.lastSync)}` : t('top.waiting');
  const canDelegate = Boolean(state.doctor?.codex_path) && gateways.some((g) => gwOk(g));
  const newBtn = $('#new-task-button');
  newBtn.disabled = !canDelegate;
  newBtn.title = canDelegate ? '' : t('gw.needGateway');
}

/* ================= overview ================= */
function renderOverview() {
  const gateways = state.doctor?.gateways || [];
  $('#overview-gateways').innerHTML = gateways.length ? gateways.map((g) => {
    const ok = gwOk(g);
    const caps = (g.capabilities || []);
    return `<div class="gw-card ${ok ? 'ok' : 'bad'}">
      <span class="gw-dot"></span>
      <div><b>${escapeHtml(g.name)}</b>${g.default ? ' <span class="default-chip">default</span>' : ''}
        <div class="cap-chips">${caps.length ? caps.map((c) => `<span class="cap-chip">${escapeHtml(c)}</span>`).join('') : '<span class="cap-chip none">no caps</span>'}</div>
      </div>
      <div class="gw-meta"><em>${ok ? t('gw.online') : t('gw.offline')}</em><small>${escapeHtml(g.response_mode === 'native' ? 'native' : 'translated')}</small></div>
    </div>`;
  }).join('') || `<p class="pempty">${t('overview.noGateway')}</p>` : `<p class="pempty">${t('overview.noGateway')}</p>`;

  const cache = state.cache;
  const target = cache?.target;
  const rate = target?.verified_warm_hit_rate;
  const targetRate = target?.hit_rate;
  const statusLabels = {
    achieved: t('cache.achieved', { r: targetRate == null ? '' : `${Math.round(targetRate * 100)}% ` }),
    below_target: t('cache.below'), insufficient_samples: t('cache.insufficient'), unverified_route: t('cache.unverified'),
  };
  const status = target?.status || 'insufficient_samples';
  const lab = state.doctor?.cache_lab || {};
  const cohorts = (cache?.cohorts || []).slice(0, 4);
  $('#overview-cache').innerHTML = `<div class="cache-hero">
    <div class="target-banner">
      <span class="big">${rate == null ? '—' : `${(rate * 100).toFixed(1)}%`}</span>
      <span class="target-badge ${escapeHtml(status)}">${escapeHtml(statusLabels[status] || status)}</span>
    </div>
    <div class="hit-row"><div class="hitbar"><i style="width:${rate == null ? 0 : Math.min(100, rate * 100)}%"></i></div></div>
    <small>${escapeHtml(t('cache.ofTarget', { r: targetRate == null ? '—' : `${Math.round(targetRate * 100)}%`, n: lab.min_warm_samples ?? '—' }))}</small>
    <div class="cache-cohort-mini">${cohorts.map((item) => `<div class="cache-mini-row">
      <span class="mono" title="${escapeHtml(item.cache_cohort || '')}">${escapeHtml(item.model || 'unknown')} · ${escapeHtml(item.gateway || '')}</span>
      <div class="hitbar"><i style="width:${item.verified_cache_hit_rate == null ? 0 : Math.min(100, item.verified_cache_hit_rate * 100)}%"></i></div>
      <span class="mono">${item.verified_cache_hit_rate == null ? '—' : `${(item.verified_cache_hit_rate * 100).toFixed(0)}%`}</span>
    </div>`).join('') || `<small>${t('cache.noSamples')}</small>`}</div>
  </div>`;

  const approvals = state.tasks.filter((x) => x.status === 'awaiting_approval');
  $('#approval-count-chip').textContent = approvals.length;
  $('#overview-approvals').innerHTML = approvals.map((task) => `<div class="approval-item">
    <span class="mini-avatar ${escapeHtml(task.kind)}">${escapeHtml((task.profile || roleLabel(task.kind)).slice(0, 1).toUpperCase())}</span>
    <div class="obj"><strong title="${escapeHtml(task.objective)}">${escapeHtml(task.objective)}</strong><small>${escapeHtml(task.model)} · ${escapeHtml(task.gateway || 'legacy')} · ${escapeHtml(shortId(task.id))}</small></div>
    <div class="actions">
      <button class="btn approve" data-approve="${escapeHtml(task.id)}" data-approval-id="${escapeHtml(task.approval_id || '')}" data-scope-digest="${escapeHtml(task.approval_scope_digest || '')}">${t('action.approve')}</button>
      <button class="btn danger" data-cancel="${escapeHtml(task.id)}">${t('action.cancel')}</button>
    </div>
  </div>`).join('') || `<p class="pempty">${t('overview.noApprovals')}</p>`;

  const recent = state.tasks.slice().sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 8);
  $('#overview-recent').innerHTML = recent.map((task) => `<div class="recent-item" data-open-task="${escapeHtml(task.id)}" role="button" tabindex="0">
    <span class="mini-avatar ${escapeHtml(task.kind)}">${escapeHtml((task.profile || roleLabel(task.kind)).slice(0, 1).toUpperCase())}</span>
    <div class="obj"><strong>${escapeHtml(task.objective)}</strong><small>${escapeHtml(task.profile || roleLabel(task.kind))} · ${escapeHtml(task.model)}</small></div>
    <span class="status ${escapeHtml(task.status)}">${escapeHtml(statusLabel(task.status))}</span>
    <time title="${escapeHtml(fmtAbs(task.created_at))}">${escapeHtml(relTime(task.created_at))}</time>
  </div>`).join('') || `<p class="pempty">${t('overview.noRecent')}</p>`;
}

/* ================= tasks ================= */
const KANBAN_COLUMNS = [
  { key: 'queued', labelKey: 'col.queued', match: ['queued'] },
  { key: 'running', labelKey: 'col.running', match: ['running', 'starting'] },
  { key: 'awaiting_approval', labelKey: 'col.awaiting_approval', match: ['awaiting_approval'] },
  { key: 'completed', labelKey: 'col.completed', match: ['completed'] },
  { key: 'failed', labelKey: 'col.failed', match: ['failed', 'blocked', 'orphaned', 'cancelled'] },
];
const FILTERS = [
  { key: '', labelKey: 'filter.all', match: null },
  { key: 'running', labelKey: 'col.running', match: ['running', 'starting'] },
  { key: 'queued', labelKey: 'col.queued', match: ['queued'] },
  { key: 'awaiting_approval', labelKey: 'col.awaiting_approval', match: ['awaiting_approval'] },
  { key: 'completed', labelKey: 'col.completed', match: ['completed'] },
  { key: 'failed', labelKey: 'filter.failed', match: ['failed', 'blocked', 'orphaned', 'cancelled'] },
];
function filteredTasks() {
  const query = state.search.toLowerCase();
  const filter = FILTERS.find((f) => f.key === state.status) || FILTERS[0];
  return state.tasks.filter((task) => {
    const statusMatch = !filter.match || filter.match.includes(task.status);
    const text = `${task.id} ${task.objective} ${task.profile || ''} ${task.model} ${task.upstream_model || ''} ${task.gateway || ''} ${task.kind}`.toLowerCase();
    return statusMatch && (!query || text.includes(query));
  });
}
function renderFilterChips() {
  const c = counts();
  $('#filter-chips').innerHTML = FILTERS.map((f) => {
    const n = !f.match ? state.tasks.length : state.tasks.filter((task) => f.match.includes(task.status)).length;
    return `<button type="button" class="fchip ${state.status === f.key ? 'active' : ''}" data-status="${escapeHtml(f.key)}">${escapeHtml(t(f.labelKey))}<b>${n}</b></button>`;
  }).join('');
}
function taskCard(task) {
  return `<article class="kcard" data-open-task="${escapeHtml(task.id)}" tabindex="0" role="button" title="${escapeHtml(task.objective)}">
    <div class="kcard-top">
      <span class="mini-avatar ${escapeHtml(task.kind)}">${escapeHtml((task.profile || roleLabel(task.kind)).slice(0, 1).toUpperCase())}</span>
      <div class="kcard-who"><strong>${escapeHtml(task.profile || roleLabel(task.kind))}</strong><small>${escapeHtml(task.model)} · ${escapeHtml(task.gateway || 'legacy')}</small></div>
    </div>
    <p class="kcard-obj">${escapeHtml(task.objective)}</p>
    <div class="kcard-foot"><span class="status ${escapeHtml(task.status)}">${escapeHtml(statusLabel(task.status))}</span><time title="${escapeHtml(fmtAbs(task.created_at))}">${escapeHtml(relTime(task.created_at))}</time></div>
  </article>`;
}
function renderTasks() {
  if (state.view !== 'tasks') return;
  renderFilterChips();
  const tasks = filteredTasks();
  const board = state.boardList === 'board';
  $('#kanban-board').hidden = !board;
  $('#list-card').hidden = board;
  $('#empty-state').hidden = tasks.length > 0;
  if (board) {
    $('#kanban-board').innerHTML = KANBAN_COLUMNS.map((col) => {
      const items = tasks.filter((task) => col.match.includes(task.status));
      return `<section class="kcol" data-col="${escapeHtml(col.key)}">
        <header class="kcol-head"><span class="kdot"></span><span>${escapeHtml(t(col.labelKey))}</span><b>${items.length}</b></header>
        <div class="kcards">${items.map(taskCard).join('') || `<div class="kempty">${t('kanban.empty')}</div>`}</div>
      </section>`;
    }).join('');
  } else {
    $('#task-body').innerHTML = tasks.map((task) => `<tr data-task-id="${escapeHtml(task.id)}">
      <td class="task-name"><strong title="${escapeHtml(task.objective)}">${escapeHtml(task.objective)}</strong><small>${escapeHtml(task.id)}</small></td>
      <td class="model-cell"><span>${escapeHtml(task.profile || roleLabel(task.kind))}</span><small>${escapeHtml(task.model)} · ${escapeHtml(task.gateway || 'legacy')}</small></td>
      <td><span class="status ${escapeHtml(task.status)}">${escapeHtml(statusLabel(task.status))}</span></td>
      <td><span title="${escapeHtml(fmtAbs(task.created_at))}">${escapeHtml(relTime(task.created_at))}</span></td>
      <td><button class="row-action" data-open-task="${escapeHtml(task.id)}">${t('common.view')}</button></td>
    </tr>`).join('');
  }
}

/* ================= cache lab ================= */
function renderCacheLab() {
  const cache = state.cache;
  const target = cache?.target;
  const rate = target?.verified_warm_hit_rate;
  const targetRate = target?.hit_rate;
  const statusLabels = {
    achieved: t('cache.achieved', { r: targetRate == null ? '' : `${Math.round(targetRate * 100)}% ` }),
    below_target: t('cache.below'), insufficient_samples: t('cache.insufficient'), unverified_route: t('cache.unverified'),
  };
  const status = target?.status || 'insufficient_samples';
  const lab = state.doctor?.cache_lab || {};
  $('#cache-target-card').innerHTML = `<div class="card-body">
    <div class="target-banner">
      <span class="eyebrow">${t('cache.targetTitle')}</span>
      <span class="big">${rate == null ? '—' : `${(rate * 100).toFixed(1)}%`}</span>
      <span class="target-badge ${escapeHtml(status)}">${escapeHtml(statusLabels[status] || status)}</span>
      <small>${escapeHtml(t('cache.ofTarget', { r: targetRate == null ? '—' : `${Math.round(targetRate * 100)}%`, n: lab.min_warm_samples ?? '—' }))}</small>
    </div>
    <div class="hit-row">
      <div class="hitbar-wrap"><div class="hitbar"><i style="width:${rate == null ? 0 : Math.min(100, rate * 100)}%"></i></div>
        ${targetRate == null ? '' : `<span class="target-tick" style="left:${Math.min(100, targetRate * 100)}%"></span>`}</div>
      <small>${targetRate == null ? '' : `${Math.round(targetRate * 100)}%`}</small>
    </div>
  </div>`;
  const cohorts = cache?.cohorts || [];
  $('#cache-cohort-body').innerHTML = cohorts.map((item) => `<tr>
    <td class="task-name"><strong title="${escapeHtml(item.cache_cohort || '')}">${escapeHtml(t('cache.cohortOf', { c: (item.cache_cohort || 'unknown').slice(-12) }))}</strong><small>${escapeHtml((item.cache_cohort_sha256 || '').slice(0, 12))}</small></td>
    <td class="model-cell"><span>${escapeHtml(item.gateway || 'unknown')}</span><small>${escapeHtml(item.model || 'unknown')}</small></td>
    <td><span class="status ${item.cohort_class === 'warm' ? 'completed' : 'queued'}">${escapeHtml(item.cohort_class === 'warm' ? t('cache.warm') : t('cache.cold'))}</span></td>
    <td>${escapeHtml(item.samples)} · ${escapeHtml(item.verified_samples)} ${t('cache.verified')}</td>
    <td style="min-width:180px"><div class="hit-row"><div class="hitbar"><i style="width:${item.verified_cache_hit_rate == null ? 0 : Math.min(100, item.verified_cache_hit_rate * 100)}%"></i></div><small>${item.verified_cache_hit_rate == null ? t('cache.unverifiedMark') : `${(item.verified_cache_hit_rate * 100).toFixed(1)}%`}</small></div></td>
  </tr>`).join('') || `<tr><td colspan="5" class="objective">${t('cache.noSamples')}</td></tr>`;
}

/* ================= system ================= */
function def(label, value, mono = false) {
  return `<div class="def"><dt>${escapeHtml(label)}</dt><dd class="${mono ? 'mono' : ''}">${value}</dd></div>`;
}
function boolSpan(value, yesText, noText) {
  return `<span class="${value ? 'bool-ok' : 'bool-bad'}">${value ? escapeHtml(yesText) : escapeHtml(noText)}</span>`;
}
function renderSystem() {
  const d = state.doctor;
  if (!d) return;
  $('#sys-runtime').innerHTML =
    def(t('sys.scheduler'), `<span class="${d.scheduler_role === 'active' ? 'routable-yes' : ''}">${escapeHtml(d.scheduler_role || '—')}</span>`) +
    def(t('sys.codex'), d.codex_path ? `${escapeHtml(d.codex_version || '')}<br><span class="mono">${escapeHtml(d.codex_path)}</span>` : `<span class="bool-bad">${t('sys.no')}</span>`) +
    def(t('sys.home'), escapeHtml(d.home || '—'), true) +
    def(t('sys.database'), escapeHtml(d.database || '—'), true) +
    def(t('sys.concurrency'), `${d.max_concurrency ?? '—'}`) +
    def(t('sys.isolated'), boolSpan(d.codex_ignore_user_config, 'on', 'off')) +
    def(t('sys.catalog'), d.codex_model_catalog ? escapeHtml(d.codex_model_catalog) : t('sys.none'), true) +
    def(t('sys.colGateway'), escapeHtml(d.default_gateway || '—'));
  const b = d.root_budget_defaults || {};
  const lab = d.cache_lab || {};
  $('#sys-budget').innerHTML =
    def(t('sys.maxSub'), `${b.max_concurrency ?? '—'}`) +
    def(t('sys.maxAttempts'), `${b.max_attempts ?? '—'}`) +
    def(t('sys.maxRetries'), `${b.max_retries ?? '—'}`) +
    def(t('sys.maxEscalations'), `${b.max_escalations ?? '—'}`) +
    def(t('sys.cacheAffinity'), boolSpan(lab.affinity_enabled, 'on', 'off')) +
    def(t('sys.cacheWindow'), `${lab.affinity_window_seconds ?? '—'} s`) +
    def(t('sys.cacheWarm'), `${lab.warm_window_seconds ?? '—'} s`) +
    def(t('sys.cacheTarget'), lab.target_hit_rate != null ? `${Math.round(lab.target_hit_rate * 100)}%` : '—') +
    def(t('sys.cacheMin'), `${lab.min_warm_samples ?? '—'}`) +
    def('Cohort', escapeHtml(lab.cohort_version || '—'), true);
  $('#sys-gateways').innerHTML = (d.gateways || []).map((g) => `<tr>
    <td><b>${escapeHtml(g.name)}</b>${g.default ? ' <span class="default-chip">default</span>' : ''}${g.enabled ? '' : ' <small>disabled</small>'}</td>
    <td>${escapeHtml(g.response_mode === 'native' ? t('protocol.native') : t('protocol.translated'))}</td>
    <td><div class="cap-chips">${(g.capabilities || []).length ? g.capabilities.map((c) => `<span class="cap-chip">${escapeHtml(c)}</span>`).join('') : '<span class="cap-chip none">—</span>'}</div></td>
    <td>${boolSpan(g.credential_configured, t('sys.yes'), t('sys.no'))}</td>
    <td><span class="reach-cell"><span class="reach-pill ${g.tcp_reachable ? 'yes' : 'no'}">TCP</span><span class="reach-pill ${g.api_reachable ? 'yes' : 'no'}">API</span></span></td>
  </tr>`).join('');
  $('#sys-models').innerHTML = (d.model_routes || []).map((r) => `<tr>
    <td class="mono-cell">${escapeHtml(r.model)}</td>
    <td>${escapeHtml(r.provider || '—')}</td>
    <td>${escapeHtml(r.billing_class || '—')}</td>
    <td class="mono-cell">${escapeHtml(r.primary || '—')}</td>
    <td>${(r.fallback || []).length ? r.fallback.map(escapeHtml).join(', ') : '<small>—</small>'}</td>
    <td><div class="cap-chips">${(r.required_capabilities || []).length ? r.required_capabilities.map((c) => `<span class="cap-chip">${escapeHtml(c)}</span>`).join('') : '<span class="cap-chip none">—</span>'}</div></td>
    <td><span class="${r.routable ? 'routable-yes' : 'routable-no'}">${r.routable ? '✓' : '✗'}</span></td>
  </tr>`).join('');
  $('#sys-profiles').innerHTML = (d.worker_profiles || []).map((p) => `<tr>
    <td><b>${escapeHtml(p.name)}</b></td>
    <td><small>${escapeHtml(p.description || '—')}</small></td>
    <td class="model-cell"><small>${escapeHtml(p.model || '—')}</small></td>
    <td>${escapeHtml(p.reasoning_effort || '—')}</td>
    <td>${escapeHtml(p.gateway || 'auto')}</td>
    <td><div class="cap-chips">${(p.allowed_kinds || []).map((k) => `<span class="cap-chip">${escapeHtml(k)}</span>`).join('')}</div></td>
  </tr>`).join('');
}

/* ================= selects ================= */
function populateSelects() {
  const d = state.doctor;
  const models = d?.allowed_models || [];
  const routes = Object.fromEntries((d?.model_routes || []).map((item) => [item.model, item]));
  for (const id of ['orchestrate-model', 'single-model']) {
    const select = $(`#${id}`);
    const previous = select.value;
    select.innerHTML = `<option value="">${t('opt.autoRoute')}</option>` + models.map((model) => {
      const r = routes[model];
      const suffix = r ? ` · ${r.provider || r.primary}${r.billing_class ? ` · ${r.billing_class}` : ''}${r.routable === false ? t('opt.notRoutable') : ''}` : '';
      return `<option value="${escapeHtml(model)}">${escapeHtml(model + suffix)}</option>`;
    }).join('');
    select.value = models.includes(previous) || previous === '' ? previous : '';
  }
  const profiles = d?.worker_profiles || [];
  for (const id of ['orchestrate-profile', 'single-profile']) {
    const select = $(`#${id}`);
    const previous = select.value;
    select.innerHTML = `<option value="">${t('opt.noProfile')}</option>` + profiles.map((p) => `<option value="${escapeHtml(p.name)}">${escapeHtml(p.name)} · ${escapeHtml(p.model)} · ${escapeHtml(p.reasoning_effort)}</option>`).join('');
    select.value = profiles.some((p) => p.name === previous) ? previous : '';
  }
  const gateways = (d?.gateways || []).filter((g) => g.enabled);
  for (const id of ['orchestrate-gateway', 'single-gateway']) {
    const select = $(`#${id}`);
    const previous = select.value;
    select.innerHTML = `<option value="">${t('opt.autoGateway')}</option>` + gateways.map((g) => {
      const protocol = g.response_mode === 'native' ? t('protocol.native') : t('protocol.translated');
      return `<option value="${escapeHtml(g.name)}">${escapeHtml(g.name)} · ${protocol}</option>`;
    }).join('');
    select.value = gateways.some((g) => g.name === previous) ? previous : '';
  }
}

/* ================= drawer ================= */
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
    $('#detail-meta').innerHTML = [statusLabel(task.status), task.profile && `${t('meta.profile')} ${task.profile}`, `${t('meta.model')} ${task.model}`,
      task.provider && `${t('meta.provider')} ${task.provider}`, task.upstream_model && `${t('meta.upstream')} ${task.upstream_model}`,
      task.gateway && `${t('meta.gateway')} ${task.gateway}`, task.execution_channel && `${t('meta.channel')} ${task.execution_channel}`, protocol,
      task.route_audit && `${t('meta.verified')} ${task.route_audit.verification}`, task.fallback_gateway && `${t('meta.fallback')} ${task.fallback_gateway}`,
      task.sandbox, fmtAbs(task.created_at), task.worktree_path].filter(Boolean).map((v) => `<span>${escapeHtml(v)}</span>`).join('');
    const actions = [];
    if (task.status === 'awaiting_approval') actions.push(`<button class="btn approve" data-approve="${escapeHtml(task.id)}" data-approval-id="${escapeHtml(task.approval_id || '')}" data-scope-digest="${escapeHtml(task.approval_scope_digest || '')}">${t('action.approve')}</button>`);
    if (!['completed', 'failed', 'cancelled', 'blocked', 'orphaned'].includes(task.status)) actions.push(`<button class="btn danger" data-cancel="${escapeHtml(task.id)}">${t('action.cancel')}</button>`);
    if (['failed', 'blocked'].includes(task.status) && task.fallback_gateway && ['plan', 'explore', 'review'].includes(task.kind)) actions.push(`<button class="btn" data-fallback="${escapeHtml(task.id)}">${escapeHtml(t('action.fallback', { gw: task.fallback_gateway }))}</button>`);
    if ((['failed', 'blocked'].includes(task.status) || task.schema?.valid === false) && ['explore', 'review'].includes(task.kind)) actions.push(`<button class="btn" data-escalate="${escapeHtml(task.id)}">${t('action.escalate')}</button>`);
    $('#detail-actions').innerHTML = actions.join('');
    $('#detail-route').innerHTML = prettyJson(task.route_audit, t('detail.noRoute'));
    $('#detail-result').innerHTML = prettyJson(task.result, task.error || t('detail.waitingWorker'));
    $('#detail-governance').innerHTML = prettyJson({
      approval: task.approval_scope || null, approval_scope_digest: task.approval_scope_digest || null,
      budget: task.budget || null, schema: task.schema || null, cache: task.cache_audit || null,
    });
    const eventIcons = { task_completed: '✓', task_failed: '✗', task_approved: '✓', task_cancelled: '×' };
    $('#detail-events').innerHTML = events.events.slice().reverse().map((ev) => `<div class="event ${escapeHtml(ev.event_type)}">
      <strong>${escapeHtml(ev.event_type)}</strong><small>${escapeHtml(fmtAbs(ev.created_at))} · ${escapeHtml(relTime(ev.created_at))}</small>
    </div>`).join('') || `<p class="objective">${t('detail.noEvents')}</p>`;
  } catch (error) { if (!silent) toast(error.message, true); }
}
function closeDrawer() {
  state.selected = null;
  $('#task-drawer').classList.remove('open');
  $('#task-drawer').setAttribute('aria-hidden', 'true');
  $('#drawer-backdrop').hidden = true;
}

/* ================= command palette ================= */
function paletteActions() {
  const actions = [
    { group: 'palette.actions', icon: '＋', label: t('palette.newTask'), hint: '', run: () => $('#task-dialog').showModal() },
    { group: 'palette.actions', icon: '⟳', label: t('top.refresh'), hint: '', run: () => refresh() },
    { group: 'palette.actions', icon: '⌫', label: t('top.purge'), hint: '', run: () => $('#purge-button').click() },
  ];
  for (const v of Object.keys(VIEWS)) {
    actions.push({ group: 'palette.actions', icon: '→', label: t('palette.goto', { view: t(VIEWS[v].title) }), hint: `#/${v}`, run: () => { location.hash = `#/${v}`; } });
  }
  return actions;
}
function openPalette() {
  $('#palette').showModal();
  $('#palette-search').value = '';
  renderPalette('');
  $('#palette-search').focus();
}
function renderPalette(query) {
  const q = query.trim().toLowerCase();
  const actions = paletteActions().filter((a) => !q || a.label.toLowerCase().includes(q));
  const tasks = state.tasks
    .filter((task) => q && `${task.id} ${task.objective} ${task.profile || ''} ${task.model}`.toLowerCase().includes(q))
    .slice(0, 8)
    .map((task) => ({ group: 'palette.tasks', icon: (task.profile || roleLabel(task.kind)).slice(0, 1).toUpperCase(), label: task.objective, hint: shortId(task.id), run: () => loadTask(task.id) }));
  const items = [...actions, ...tasks];
  state.paletteItems = items;
  state.paletteIndex = Math.min(state.paletteIndex, Math.max(0, items.length - 1));
  const list = $('#palette-list');
  if (!items.length) { list.innerHTML = `<div class="pempty">${t('palette.noResult')}</div>`; return; }
  let lastGroup = null;
  list.innerHTML = items.map((item, i) => {
    const header = item.group !== lastGroup ? `<div class="pgroup">${t(item.group)}</div>` : '';
    lastGroup = item.group;
    return `${header}<button type="button" class="pitem ${i === state.paletteIndex ? 'sel' : ''}" data-pi="${i}">
      <span class="pico">${escapeHtml(item.icon)}</span><span class="plabel">${escapeHtml(item.label)}</span><span class="phint">${escapeHtml(item.hint)}</span>
    </button>`;
  }).join('');
}

/* ================= data refresh ================= */
async function refresh(silent = false) {
  try {
    const [doctor, tasks, cache] = await Promise.all([api('/api/doctor'), api('/api/tasks?limit=500'), api('/api/cache-metrics?model=deepseek%2Fdeepseek-v4-flash')]);
    state.doctor = doctor;
    state.tasks = tasks.tasks || [];
    state.cache = cache;
    state.lastSync = Date.now();
    updateMetrics();
    renderCurrentView();
    updateHealth();
    populateSelects();
    if (state.selected) await loadTask(state.selected, true);
    if (!silent) toast(t('toast.refreshed'));
  } catch (error) {
    updateHealth();
    if (!silent) toast(error.message, true);
  }
}

/* ================= form submit ================= */
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
    required_capabilities: $('#single-capabilities').value.split(',').map((v) => v.trim()).filter(Boolean),
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

/* ================= actions (delegated) ================= */
document.addEventListener('click', async (event) => {
  const open = event.target.closest('[data-open-task]');
  if (open) return loadTask(open.dataset.openTask);
  if (event.target.closest('[data-open-new]')) return $('#task-dialog').showModal();
  const approve = event.target.closest('[data-approve]');
  if (approve) {
    const body = { approval_id: approve.dataset.approvalId || null, scope_digest: approve.dataset.scopeDigest || null };
    try { await api(`/api/tasks/${encodeURIComponent(approve.dataset.approve)}/approve`, { method: 'POST', body: JSON.stringify(body) }); toast(t('toast.approved')); await refresh(true); } catch (error) { toast(error.message, true); }
    return;
  }
  const cancel = event.target.closest('[data-cancel]');
  if (cancel && confirm(t('confirm.cancel'))) {
    try { await api(`/api/tasks/${encodeURIComponent(cancel.dataset.cancel)}/cancel`, { method: 'POST', body: '{}' }); toast(t('toast.cancelSent')); await refresh(true); } catch (error) { toast(error.message, true); }
    return;
  }
  const fallback = event.target.closest('[data-fallback]');
  if (fallback && confirm(t('confirm.fallback'))) {
    try { const result = await api(`/api/tasks/${encodeURIComponent(fallback.dataset.fallback)}/retry-fallback`, { method: 'POST', body: '{}' }); toast(t('toast.fallbackQueued', { id: result.task_id })); await refresh(true); await loadTask(result.task_id); } catch (error) { toast(error.message, true); }
    return;
  }
  const escalate = event.target.closest('[data-escalate]');
  if (escalate && confirm(t('confirm.escalate'))) {
    try { const result = await api(`/api/tasks/${encodeURIComponent(escalate.dataset.escalate)}/escalate`, { method: 'POST', body: '{}' }); toast(t('toast.escalateQueued', { id: result.task_id })); await refresh(true); await loadTask(result.task_id); } catch (error) { toast(error.message, true); }
  }
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && event.target.closest('.kcard, .recent-item')) { event.target.closest('.kcard, .recent-item').click(); }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); if ($('#palette').open) $('#palette').close(); else openPalette(); return; }
  if (event.key === 'Escape') closeDrawer();
});

/* nav + toolbar */
$$('.nav-link').forEach((a) => a.addEventListener('click', (event) => { event.preventDefault(); location.hash = a.getAttribute('href'); }));
$$('.view-btn').forEach((button) => button.addEventListener('click', () => {
  state.boardList = button.dataset.view;
  localStorage.setItem('lw-view', state.boardList);
  $$('.view-btn').forEach((b) => b.classList.toggle('active', b === button));
  renderTasks();
}));
function setLanguage(lang) {
  state.lang = lang;
  localStorage.setItem('lw-lang', lang);
  applyI18n();
  updateMetrics();
  renderCurrentView();
  updateHealth();
  populateSelects();
  if (state.selected) loadTask(state.selected, true);
  toast(t(lang === 'zh' ? 'toast.langZh' : 'toast.langEn'));
}
$$('.lang-btn').forEach((button) => button.addEventListener('click', () => setLanguage(button.dataset.lang)));
$$('.tab').forEach((button) => button.addEventListener('click', () => {
  $$('.tab').forEach((item) => item.classList.toggle('active', item === button));
  $$('#task-form-shell .tab-pane').forEach((pane) => pane.hidden = pane.id !== `pane-${button.dataset.tab}`);
}));
$$('.dtab').forEach((button) => button.addEventListener('click', () => {
  $$('.dtab').forEach((item) => item.classList.toggle('active', item === button));
  $$('.dpane').forEach((pane) => pane.hidden = pane.dataset.dpane !== button.dataset.dtab);
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
$('#palette-button').addEventListener('click', openPalette);
$('#palette-search').addEventListener('input', (event) => { state.paletteIndex = 0; renderPalette(event.target.value); });
$('#palette-list').addEventListener('click', (event) => {
  const item = event.target.closest('[data-pi]');
  if (!item) return;
  const entry = state.paletteItems[Number(item.dataset.pi)];
  $('#palette').close();
  if (entry) entry.run();
});
$('#palette-search').addEventListener('keydown', (event) => {
  if (event.key === 'ArrowDown') { event.preventDefault(); state.paletteIndex = Math.min(state.paletteIndex + 1, state.paletteItems.length - 1); renderPalette($('#palette-search').value); }
  else if (event.key === 'ArrowUp') { event.preventDefault(); state.paletteIndex = Math.max(state.paletteIndex - 1, 0); renderPalette($('#palette-search').value); }
  else if (event.key === 'Enter') { event.preventDefault(); const entry = state.paletteItems[state.paletteIndex]; $('#palette').close(); if (entry) entry.run(); }
});
window.addEventListener('hashchange', applyRoute);

/* relative-time ticker */
setInterval(() => {
  if (document.hidden) return;
  $('#scheduler-sync').textContent = state.lastSync ? `${t('top.refresh')} · ${relTime(state.lastSync)}` : t('top.waiting');
  if (state.view === 'tasks') { /* keep board times fresh on next refresh cycle */ }
}, 10000);

applyI18n();
$$('#task-form-shell .tab-pane').forEach((pane) => pane.hidden = !pane.classList.contains('active'));
$$('.dpane').forEach((pane) => pane.hidden = pane.dataset.dpane !== 'overview');
applyRoute();
refresh(true);
setInterval(() => { if (!document.hidden) refresh(true); }, 3000);
