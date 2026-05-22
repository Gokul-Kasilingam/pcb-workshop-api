const tokenKey = 'pcbWorkshopAdminToken';
let token = localStorage.getItem(tokenKey) || '';
let teamsCache = [];
let questionsCache = [];

const loginView = document.getElementById('loginView');
const appView = document.getElementById('appView');
const pageTitle = document.getElementById('pageTitle');

function setMessage(id, text, ok = true) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = `message ${ok ? 'ok' : 'err'}`;
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...options, headers });
  const contentType = res.headers.get('content-type') || '';
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      detail = err.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  if (contentType.includes('application/json')) return res.json();
  return res.blob();
}

function showApp() {
  loginView.classList.add('hidden');
  appView.classList.remove('hidden');
  loadAll();
}

function showLogin() {
  appView.classList.add('hidden');
  loginView.classList.remove('hidden');
}

function renderTable(tableId, rows, columns, actions) {
  const table = document.getElementById(tableId);
  if (!table) return;
  if (!rows || rows.length === 0) {
    table.innerHTML = `<thead><tr><th>No data yet</th></tr></thead><tbody><tr><td>Add records to see them here.</td></tr></tbody>`;
    return;
  }
  const cols = columns || Object.keys(rows[0]);
  const actionHead = actions ? '<th>Action</th>' : '';
  table.innerHTML = `
    <thead><tr>${cols.map(c => `<th>${labelize(c)}</th>`).join('')}${actionHead}</tr></thead>
    <tbody>${rows.map(row => `<tr>${cols.map(c => `<td>${escapeHtml(row[c] ?? '')}</td>`).join('')}${actions ? `<td>${actions(row)}</td>` : ''}</tr>`).join('')}</tbody>
  `;
}

function labelize(text) {
  return String(text).replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

function formToObject(form) {
  const fd = new FormData(form);
  const obj = {};
  for (const [key, value] of fd.entries()) obj[key] = value;
  form.querySelectorAll('input[type="checkbox"]').forEach(input => { obj[input.name] = input.checked; });
  return obj;
}

async function loadDashboard() {
  const stats = await api('/api/dashboard/stats');
  const labels = {
    participants: 'Participants', teams: 'Teams', quiz_questions: 'Quiz Questions', quiz_results: 'Quiz Results', game_scores: 'Game Scores'
  };
  document.getElementById('statsCards').innerHTML = Object.entries(labels).map(([key, label]) => `
    <div class="stat-card"><strong>${stats[key]}</strong><span>${label}</span></div>
  `).join('');
}

async function loadParticipants() {
  const rows = await api('/api/participants');
  renderTable('participantsTable', rows, ['participant_id','name','phone','email','college','department','year','created_at'], row => `<button class="danger" onclick="deleteParticipant('${row.participant_id}')">Delete</button>`);
}

async function deleteParticipant(id) {
  if (!confirm('Delete this participant?')) return;
  await api(`/api/participants/${id}`, { method: 'DELETE' });
  await loadParticipants();
  await loadDashboard();
}

async function loadTeams() {
  teamsCache = await api('/api/teams');
  const members = await api('/api/team-members');
  fillTeamSelects();
  renderTable('teamMembersTable', members, ['team_id','team_name','participant_id','participant_name','department','year','member_role']);
}

function fillTeamSelects() {
  const options = teamsCache.map(t => `<option value="${t.team_id}">${escapeHtml(t.team_name)} (${t.team_id})</option>`).join('');
  ['quizTeamSelect','gameTeamSelect'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = options || '<option value="">No teams</option>';
  });
}

async function loadQuiz() {
  questionsCache = await api('/api/quiz/questions');
  const results = await api('/api/quiz/results');
  await loadTeams();
  renderQuizQuestions();
  renderTable('quizResultsTable', results, ['result_id','team_id','total_score','max_score','created_at','answers_json']);
}

function renderQuizQuestions() {
  const box = document.getElementById('quizQuestionList');
  if (!questionsCache.length) {
    box.innerHTML = '<p>No questions yet.</p>';
    return;
  }
  box.innerHTML = questionsCache.map(q => `
    <div class="question-card">
      <strong>Q${q.question_id}. ${escapeHtml(q.question)} <small>(${q.points} pts)</small></strong>
      <div class="answer-row">
        ${['A','B','C','D'].map(opt => `<label><input type="radio" name="q_${q.question_id}" value="${opt}"> ${opt}. ${escapeHtml(q[`option_${opt.toLowerCase()}`])}</label>`).join('')}
      </div>
    </div>
  `).join('');
}

async function loadGames() {
  await loadTeams();
  const scores = await api('/api/games/scores');
  renderTable('gameScoresTable', scores, ['score_id','team_id','game_name','score','max_score','notes','created_at'], row => `<button class="danger" onclick="deleteGameScore('${row.score_id}')">Delete</button>`);
}

async function deleteGameScore(id) {
  if (!confirm('Delete this score?')) return;
  await api(`/api/games/scores/${id}`, { method: 'DELETE' });
  await loadGames();
  await loadLeaderboard();
}

async function loadLeaderboard() {
  const rows = await api('/api/leaderboard');
  renderTable('leaderboardTable', rows, ['team_name','quiz_score','game_score','total_score','updated_at']);
}

async function loadCsvTools() {
  const data = await api('/api/csv/tables');
  const box = document.getElementById('csvButtons');
  box.innerHTML = data.tables.map(table => `
    <div class="csv-card">
      <strong>${labelize(table)}</strong>
      <button class="ghost" onclick="downloadCsv('${table}')">Download CSV</button>
      <label>Import CSV<input type="file" accept=".csv" onchange="importCsv('${table}', this.files[0])"></label>
    </div>
  `).join('');
}

async function downloadCsv(table) {
  const blob = await api(`/api/csv/${table}`);
  downloadBlob(blob, `${table}.csv`);
}

async function importCsv(table, file) {
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  await api(`/api/csv/${table}/import`, { method: 'POST', body: fd, headers: { Authorization: `Bearer ${token}` } });
  alert(`${table}.csv imported`);
  await loadAll();
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function loadAll() {
  try {
    await loadDashboard();
    await loadParticipants();
    await loadTeams();
    await loadQuiz();
    await loadGames();
    await loadLeaderboard();
    await loadCsvTools();
  } catch (err) {
    console.error(err);
    if (String(err.message).toLowerCase().includes('token')) logout();
  }
}

function logout() {
  token = '';
  localStorage.removeItem(tokenKey);
  showLogin();
}

document.getElementById('loginForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    const res = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
    token = res.token;
    localStorage.setItem(tokenKey, token);
    setMessage('loginMessage', 'Login successful');
    showApp();
  } catch (err) {
    setMessage('loginMessage', err.message, false);
  }
});

document.querySelectorAll('nav button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');
    pageTitle.textContent = labelize(btn.dataset.tab);
  });
});

document.getElementById('logoutBtn').addEventListener('click', logout);
document.getElementById('refreshBtn').addEventListener('click', loadAll);

document.getElementById('participantForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    await api('/api/participants', { method: 'POST', body: JSON.stringify(formToObject(e.target)) });
    e.target.reset();
    setMessage('participantMsg', 'Participant registered');
    await loadParticipants();
    await loadDashboard();
  } catch (err) { setMessage('participantMsg', err.message, false); }
});

document.getElementById('teamForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const data = formToObject(e.target);
    data.team_size = Number(data.team_size);
    const res = await api('/api/teams/generate', { method: 'POST', body: JSON.stringify(data) });
    setMessage('teamMsg', `${res.team_count} teams generated for ${res.participant_count} participants`);
    await loadTeams();
    await loadLeaderboard();
    await loadDashboard();
  } catch (err) { setMessage('teamMsg', err.message, false); }
});

document.getElementById('resetTeamsBtn').addEventListener('click', async () => {
  if (!confirm('Reset all teams?')) return;
  await api('/api/teams/reset', { method: 'DELETE' });
  await loadTeams();
  await loadLeaderboard();
  setMessage('teamMsg', 'Teams reset');
});

document.getElementById('questionForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const data = formToObject(e.target);
    data.points = Number(data.points);
    await api('/api/quiz/questions', { method: 'POST', body: JSON.stringify(data) });
    e.target.reset();
    setMessage('questionMsg', 'Question added');
    await loadQuiz();
  } catch (err) { setMessage('questionMsg', err.message, false); }
});

document.getElementById('submitQuizBtn').addEventListener('click', async () => {
  try {
    const team_id = document.getElementById('quizTeamSelect').value;
    const answers = {};
    questionsCache.forEach(q => {
      const selected = document.querySelector(`input[name="q_${q.question_id}"]:checked`);
      if (selected) answers[q.question_id] = selected.value;
    });
    const res = await api('/api/quiz/submit', { method: 'POST', body: JSON.stringify({ team_id, answers }) });
    setMessage('quizMsg', `Score saved: ${res.total_score}/${res.max_score}`);
    await loadQuiz();
    await loadLeaderboard();
  } catch (err) { setMessage('quizMsg', err.message, false); }
});

document.getElementById('gameScoreForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const data = formToObject(e.target);
    data.score = Number(data.score);
    data.max_score = Number(data.max_score);
    await api('/api/games/scores', { method: 'POST', body: JSON.stringify(data) });
    e.target.reset();
    setMessage('gameMsg', 'Game score saved');
    await loadGames();
    await loadLeaderboard();
    await loadDashboard();
  } catch (err) { setMessage('gameMsg', err.message, false); }
});

document.getElementById('downloadAllCsvBtn').addEventListener('click', async () => {
  const blob = await api('/api/csv/export/all');
  downloadBlob(blob, 'pcb_workshop_csv_database.zip');
});

document.getElementById('passwordForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const data = formToObject(e.target);
    await api('/api/admin/change-password', { method: 'POST', body: JSON.stringify(data) });
    e.target.reset();
    setMessage('passwordMsg', 'Password changed. Please login again.');
    setTimeout(logout, 800);
  } catch (err) { setMessage('passwordMsg', err.message, false); }
});

if (token) showApp(); else showLogin();
