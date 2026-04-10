
let token = localStorage.getItem('ds_token') || '';
let selectedUpload = null;
let lastMaskResult = null;
let dbCache = [];
let lastCoverageReport = null;

function authHeaders(extra = {}) {
  const headers = {...extra};
  if (token) headers['Authorization'] = 'Bearer ' + token;
  return headers;
}

function setOutput(id, data) {
  document.getElementById(id).textContent = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
}

function setSession(text, isOk = true) {
  const el = document.getElementById('session_state');
  el.textContent = text;
  el.style.borderColor = isOk ? 'rgba(29,194,160,.35)' : 'rgba(255,105,120,.35)';
  el.style.background = isOk ? 'rgba(29,194,160,.09)' : 'rgba(255,105,120,.08)';
}

async function api(path, opts = {}) {
  const method = opts.method || 'GET';
  const init = {method, headers: authHeaders(opts.headers || {})};
  if (opts.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  if (opts.formData) {
    delete init.headers['Content-Type'];
    init.body = opts.formData;
  }
  const res = await fetch(path, init);
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = text; }
  if (!res.ok) throw new Error(typeof data === 'string' ? data : JSON.stringify(data));
  return data;
}

async function login() {
  try {
    const data = await api('/api/auth/login', {method:'POST', body:{username:login_user.value.trim(), password:login_pass.value.trim()}});
    token = data.token;
    localStorage.setItem('ds_token', token);
    setOutput('auth_output', data);
    setSession(`Авторизован: ${data.username} (${data.role})`);
    await refreshDashboard();
  } catch (e) {
    setOutput('auth_output', String(e));
    setSession('Ошибка авторизации', false);
  }
}

async function whoAmI() {
  try {
    const data = await api('/api/auth/me');
    setOutput('auth_output', data);
    setSession(`Авторизован: ${data.username} (${data.role})`);
  } catch (e) {
    setOutput('auth_output', String(e));
    setSession('Сессия недоступна', false);
  }
}

async function logout() {
  try { await api('/api/auth/logout', {method:'POST'}); } catch {}
  token = '';
  localStorage.removeItem('ds_token');
  setSession('Не авторизован', false);
  setOutput('auth_output', 'Выход выполнен.');
}

async function maskPreview() {
  try {
    const data = await api('/api/mask', {method:'POST', body:{service:svc.value, value:val.value, mode:preview_mode.value}});
    setOutput('preview_output', data);
  } catch (e) {
    setOutput('preview_output', String(e));
  }
}

async function uploadDatabase() {
  const fileInput = document.getElementById('db_file');
  if (!fileInput.files.length) {
    setOutput('upload_output', 'Сначала выберите SQLite-файл.');
    return;
  }
  const fd = new FormData();
  fd.append('file', fileInput.files[0]);
  try {
    const data = await api('/api/databases/upload', {method:'POST', formData:fd});
    selectedUpload = data;
    renderSelectedUpload(data);
    setOutput('upload_output', data);
    document.getElementById('mask_status').textContent = `База ${data.saved_name} загружена. Рекомендуется сначала выполнить анализ покрытия.`;
    document.getElementById('coverage_status').textContent = `Найдено потенциально чувствительных колонок: ${data.analysis_summary?.detected_columns ?? 0}`;
    await refreshDashboard();
  } catch (e) {
    setOutput('upload_output', String(e));
    document.getElementById('mask_status').textContent = 'Загрузка не выполнена.';
  }
}

async function analyzeSelectedDatabase() {
  if (!selectedUpload) {
    setOutput('coverage_output', 'Сначала загрузите или выберите базу из реестра.');
    return;
  }
  document.getElementById('coverage_status').textContent = 'Выполняется анализ покрытия...';
  try {
    const data = await api('/api/databases/analyze', {method:'POST', body:{upload_id:selectedUpload.upload_id}});
    lastCoverageReport = data;
    setOutput('coverage_output', data);
    const box = document.getElementById('coverage_summary');
    box.classList.remove('hidden');
    box.innerHTML = `
      <strong>Coverage pre-check</strong><br>
      <span class="mini">Таблиц: ${data.summary.tables}</span><br>
      <span class="mini">Найдено колонок: ${data.summary.detected_columns}</span><br>
      <span class="mini">High risk: ${data.summary.high_risk_detected} · Medium risk: ${data.summary.medium_risk_detected} · Low risk: ${data.summary.low_risk_detected}</span>
    `;
    document.getElementById('coverage_status').textContent = 'Анализ покрытия завершён.';
    document.getElementById('stat_coverage').textContent = 'pre';
  } catch (e) {
    setOutput('coverage_output', String(e));
    document.getElementById('coverage_status').textContent = 'Анализ завершился с ошибкой.';
  }
}


async function downloadWithAuth(url, filename) {
  try {
    const res = await fetch(url, {
      headers: authHeaders({})
    });
    if (!res.ok) {
      const msg = await res.text();
      throw new Error(msg || `Download failed: ${res.status}`);
    }
    const blob = await res.blob();
    const href = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = href;
    a.download = filename || 'download.bin';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(href);
  } catch (e) {
    setOutput('mask_output', String(e));
    document.getElementById('mask_status').textContent = 'Скачивание завершилось с ошибкой.';
  }
}

function fileNameFromUrl(url, fallbackName) {
  if (!url) return fallbackName || 'download.bin';
  const clean = String(url).split('?')[0];
  const parts = clean.split('/');
  return parts[parts.length - 1] || fallbackName || 'download.bin';
}

function renderCoverageReport(report) {
  lastCoverageReport = report;
  const s = report.summary || {};
  document.getElementById('stat_coverage').textContent = `${s.coverage_percent ?? 0}%`;
  document.getElementById('coverage_status').textContent = `Покрытие маскирования: ${s.coverage_percent ?? 0}%`;
  setOutput('coverage_output', report);
  const box = document.getElementById('coverage_summary');
  box.classList.remove('hidden');
  box.innerHTML = `
    <strong>Coverage report</strong><br>
    <span class="mini">Detected columns: ${s.detected_columns ?? 0}</span><br>
    <span class="mini">Changed columns: ${s.changed_columns ?? 0} · Unchanged columns: ${s.unchanged_columns ?? 0}</span><br>
    <span class="mini">High-risk unmasked: ${s.high_risk_unmasked ?? 0} · Medium-risk unmasked: ${s.medium_risk_unmasked ?? 0}</span><br>
    <span class="mini">JSON: <button class="btn-ghost" style="padding:6px 10px;margin-left:6px" onclick="downloadWithAuth('${report.download_report_json_url}', fileNameFromUrl('${report.download_report_json_url}', 'coverage_report.json'))">скачать JSON report</button></span><br>
    <span class="mini">CSV: <button class="btn-ghost" style="padding:6px 10px;margin-left:6px" onclick="downloadWithAuth('${report.download_report_csv_url}', fileNameFromUrl('${report.download_report_csv_url}', 'coverage_report.csv'))">скачать CSV report</button></span>
  `;
}

async function loadCoverageReport() {
  if (!lastMaskResult?.job_id) {
    setOutput('coverage_output', 'Сначала выполните маскирование или получите job_id.');
    return;
  }
  try {
    const data = await api(`/api/reports/${lastMaskResult.job_id}`);
    renderCoverageReport(data);
  } catch (e) {
    setOutput('coverage_output', String(e));
  }
}

function renderSelectedUpload(data) {
  const box = document.getElementById('selected_db_box');
  box.classList.remove('hidden');
  box.innerHTML = `
    <strong>Выбрана база:</strong> ${data.saved_name}<br>
    <span class="mini">Путь: ${data.saved_path}</span><br>
    <span class="mini">Таблиц: ${data.table_count} · Оценка строк: ${data.detected_rows}</span>
  `;
}

async function runDatabaseMasking() {
  if (!selectedUpload) {
    setOutput('mask_output', 'Сначала загрузите или выберите базу из реестра.');
    return;
  }
  document.getElementById('mask_status').textContent = 'Маскирование выполняется. Не закрывайте вкладку до получения результата.';
  try {
    const data = await api('/api/databases/mask', {method:'POST', body:{upload_id:selectedUpload.upload_id, mode:db_mask_mode.value}});
    lastMaskResult = data;
    setOutput('mask_output', data);
    document.getElementById('mask_status').textContent = data.saved_message;
    const summary = document.getElementById('result_summary');
    summary.classList.remove('hidden');
    summary.innerHTML = `
      <strong>Маскирование завершено</strong><br>
      <span class="mini">Job ID: ${data.job_id}</span><br>
      <span class="mini">Маскированная база: ${data.masked_db}</span><br>
      <span class="mini">Конфиг выполнения: ${data.config_path}</span><br>
      <span class="mini">Скачать: <button class="btn-ghost" style="padding:6px 10px;margin-left:6px" onclick="downloadWithAuth('${data.download_url}', fileNameFromUrl('${data.download_url}', 'masked_database.sqlite'))">скачать маскированную базу</button></span><br>
      <span class="mini">Coverage JSON: <button class="btn-ghost" style="padding:6px 10px;margin-left:6px" onclick="downloadWithAuth('${(data.coverage_report && data.coverage_report.download_report_json_url) ? data.coverage_report.download_report_json_url : '#'}', fileNameFromUrl('${(data.coverage_report && data.coverage_report.download_report_json_url) ? data.coverage_report.download_report_json_url : '#'}', 'coverage_report.json'))">скачать report JSON</button></span><br>
      <span class="mini">Coverage CSV: <button class="btn-ghost" style="padding:6px 10px;margin-left:6px" onclick="downloadWithAuth('${(data.coverage_report && data.coverage_report.download_report_csv_url) ? data.coverage_report.download_report_csv_url : '#'}', fileNameFromUrl('${(data.coverage_report && data.coverage_report.download_report_csv_url) ? data.coverage_report.download_report_csv_url : '#'}', 'coverage_report.csv'))">скачать report CSV</button></span>
    `;
    if (data.coverage_report) renderCoverageReport(data.coverage_report);
    await refreshDashboard();
  } catch (e) {
    setOutput('mask_output', String(e));
    document.getElementById('mask_status').textContent = 'Маскирование завершилось с ошибкой.';
  }
}

async function loadDatabases() {
  try {
    const items = await api('/api/databases');
    document.getElementById('stat_uploaded').textContent = items.length;
    dbCache = items;
    const tbody = document.getElementById('db_list');
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="mini">Загруженных баз пока нет.</td></tr>';
      return;
    }
    tbody.innerHTML = items.map((item, index) => `
      <tr>
        <td><strong>${item.name}</strong><div class="mini">${Math.round(item.size_bytes/1024)} KB</div></td>
        <td class="mini">${item.path}</td>
        <td><button class="btn-ghost" style="padding:10px 12px" onclick="selectExistingByIndex(${index})">Выбрать</button></td>
      </tr>
    `).join('');
  } catch (e) {
    setOutput('jobs_output', String(e));
  }
}

function selectExistingByIndex(index) {
  const item = dbCache[index];
  if (!item) return;
  selectedUpload = item;
  renderSelectedUpload({saved_name:item.name, saved_path:item.path, table_count:'?', detected_rows:'?', upload_id:item.upload_id});
  document.getElementById('mask_status').textContent = `Выбрана ранее загруженная база ${item.name}. Можно запускать маскирование.`;
  document.getElementById('coverage_status').textContent = 'Для этой базы доступен повторный анализ покрытия.';
}

async function queueStats() {
  try {
    const data = await api('/api/queue/stats');
    document.getElementById('stat_queued').textContent = data.queued;
    document.getElementById('stat_completed').textContent = data.completed;
    document.getElementById('stat_failed').textContent = data.failed;
    setOutput('jobs_output', data);
  } catch (e) {
    setOutput('jobs_output', String(e));
  }
}

async function listJobs() {
  try {
    const data = await api('/api/jobs');
    setOutput('jobs_output', data);
    document.getElementById('stat_completed').textContent = data.filter(x => x.status === 'completed').length;
    document.getElementById('stat_failed').textContent = data.filter(x => x.status === 'failed').length;
    document.getElementById('stat_queued').textContent = data.filter(x => x.status === 'queued').length;
  } catch (e) {
    setOutput('jobs_output', String(e));
  }
}

async function verifyAudit() {
  try {
    const data = await api('/api/audit/verify');
    setOutput('jobs_output', data);
  } catch (e) {
    setOutput('jobs_output', String(e));
  }
}

async function refreshDashboard() {
  await Promise.allSettled([loadDatabases(), queueStats()]);
}

window.addEventListener('load', async () => {
  login_user.value = '';
  login_pass.value = '';
  if (token) await whoAmI();
  await refreshDashboard();
});
