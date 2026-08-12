/* Каталог ИИ-бизнесов 2026. Маршрутизация по hash, данные — статический JSON. */
'use strict';

var FIELD_ORDER = ['one_liner', 'buyer', 'players', 'money', 'pricing', 'moat', 'capital',
  'time_to_revenue', 'foreign_dependency', 'ru_analog', 'ru_fit', 'kill_switch', 'failures',
  'proverka', 'duplicate_of', 'see_also'];

var FIELD_LABEL = {
  one_liner: 'Суть', buyer: 'Кто платит', players: 'Игроки', money: 'Деньги',
  pricing: 'Цена и модель оплаты', moat: 'Что защищает', capital: 'Капиталоёмкость',
  time_to_revenue: 'Когда первый платёж', foreign_dependency: 'Зависимость от зарубежного',
  ru_analog: 'Российский аналог', ru_fit: 'Что ломается в России',
  kill_switch: 'Что убьёт идею', failures: 'Кто пробовал и закрылся',
  proverka: 'Что изменила проверка скептиком',
  duplicate_of: 'Повтор карточки', see_also: 'Смежные карточки'
};

/* Служебные поля: вердикт показан бейджем в шапке, второй раз его печатать незачем. */
var FIELD_HIDDEN = { ru_verdict: true };

var BADGE = { 'свободно': 'b-free', 'частично': 'b-part', 'занято': 'b-taken', 'нет данных': 'b-none' };
var PAGE = 40;

var app = document.getElementById('app');
var titleEl = document.getElementById('title');
var backEl = document.getElementById('back');
var chipsEl = document.getElementById('chips');
var searchRow = document.getElementById('searchRow');
var qEl = document.getElementById('q');

var DATA = null;
var docsIndex = [];
var docCache = {};
var state = { q: '', verdict: '', family: '', shown: PAGE };

/* ------------------------------------------------------------------ утилиты */

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
  });
}

function badge(v) {
  return '<span class="badge ' + (BADGE[v] || 'b-none') + '">' + esc(v) + '</span>';
}

function setTitle(t, showBack) {
  titleEl.textContent = t;
  backEl.hidden = !showBack;
  document.title = t === 'Каталог ИИ-бизнесов' ? 'Каталог ИИ-бизнесов 2026'
    : t + ' — Каталог ИИ-бизнесов 2026';
}

function markTab(tab) {
  var links = document.querySelectorAll('.tabs a');
  for (var i = 0; i < links.length; i++) {
    if (links[i].getAttribute('data-tab') === tab) links[i].setAttribute('aria-current', 'page');
    else links[i].removeAttribute('aria-current');
  }
}

function go(hash) { location.hash = hash; }

/* -------------------------------------------------------------------- фильтр */

function filtered() {
  var q = state.q.trim().toLowerCase();
  var words = q ? q.split(/\s+/) : [];
  return DATA.ideas.filter(function (it) {
    if (state.verdict && it.verdict !== state.verdict) return false;
    if (state.family && it.family !== state.family) return false;
    for (var i = 0; i < words.length; i++) {
      if (it.search.indexOf(words[i]) === -1) return false;
    }
    return true;
  });
}

function itemHtml(it) {
  return '<a class="item" href="#/idea/' + encodeURIComponent(it.id) + '">' +
    '<div class="item-top"><span class="fam">' + esc(it.family) + '</span>' + badge(it.verdict) + '</div>' +
    '<div class="item-name">' + esc(it.name) + '</div>' +
    '<div class="item-sub">' + esc(it.one_liner || '') + '</div>' +
    (it.key_number ? '<div class="item-num">' + esc(it.key_number) + '</div>' : '') +
    '</a>';
}

/* --------------------------------------------------------------------- экраны */

function viewIdeas() {
  setTitle('Каталог ИИ-бизнесов', false);
  markTab('ideas');
  searchRow.hidden = false;
  renderChips();
  var list = filtered();
  var slice = list.slice(0, state.shown);
  var dupes = DATA.total - (DATA.distinct || DATA.total);
  var html = '<p class="count">Найдено ' + list.length + ' из ' + DATA.total +
    (dupes ? ' <span class="count-note">(' + DATA.distinct + ' различимых: ' + dupes +
      ' карточек — повтор идеи из другой семьи)</span>' : '') + '</p>';
  if (!list.length) {
    html += '<p class="empty">Ничего не нашлось. Попробуйте другое слово или снимите фильтр.</p>';
  } else {
    html += slice.map(itemHtml).join('');
    if (list.length > slice.length) {
      html += '<button class="more" id="more">Показать ещё ' +
        Math.min(PAGE, list.length - slice.length) + '</button>';
    }
  }
  app.innerHTML = html;
  var more = document.getElementById('more');
  if (more) more.onclick = function () { state.shown += PAGE; viewIdeas(); };
}

function renderChips() {
  var c = DATA.counts;
  var chips = [['', 'Все ' + DATA.total]];
  ['свободно', 'частично', 'занято', 'нет данных'].forEach(function (v) {
    if (c[v]) chips.push([v, v + ' ' + c[v]]);
  });
  var html = chips.map(function (p) {
    return '<button class="chip" data-v="' + esc(p[0]) + '" aria-pressed="' +
      (state.verdict === p[0]) + '">' + esc(p[1]) + '</button>';
  }).join('');
  html += '<button class="chip" data-fam="1" aria-pressed="' + (!!state.family) +
    '">' + (state.family ? 'Семья ' + esc(state.family) : 'Все семьи') + '</button>';
  chipsEl.innerHTML = html;
  var btns = chipsEl.querySelectorAll('.chip');
  for (var i = 0; i < btns.length; i++) {
    btns[i].onclick = function () {
      if (this.getAttribute('data-fam')) { go('#/families'); return; }
      state.verdict = this.getAttribute('data-v');
      state.shown = PAGE;
      viewIdeas();
    };
  }
}

/* Полные карточки лежат по файлу на семью и подгружаются по требованию:
   так первая загрузка на телефоне остаётся лёгкой. */
var famCache = {};

function loadFamily(code) {
  if (famCache[code]) return Promise.resolve(famCache[code]);
  return fetch('data/family/' + encodeURIComponent(code) + '.json')
    .then(function (r) { return r.json(); })
    .then(function (d) { famCache[code] = d; return d; });
}

function viewIdea(id) {
  var light = null;
  for (var i = 0; i < DATA.ideas.length; i++) if (DATA.ideas[i].id === id) { light = DATA.ideas[i]; break; }
  if (!light) { app.innerHTML = '<p class="empty">Идея не найдена.</p>'; return; }
  setTitle('Идея', true);
  markTab('ideas');
  searchRow.hidden = true;
  chipsEl.innerHTML = '';
  app.innerHTML = '<p class="loading">Загрузка карточки…</p>';
  loadFamily(light.family).then(function (fam) {
    if (location.hash.indexOf(encodeURIComponent(id)) === -1 &&
        location.hash.indexOf(id) === -1) return;
    var it = null;
    for (var j = 0; j < fam.cards.length; j++) if (fam.cards[j].id === id) { it = fam.cards[j]; break; }
    if (!it) { app.innerHTML = '<p class="empty">Карточка не найдена в файле семьи.</p>'; return; }
    renderIdea(it);
  }).catch(function () {
    app.innerHTML = '<p class="empty">Не удалось загрузить карточку.</p>';
  });
}

function renderIdea(it) {
  var html = '<div class="card-head">' +
    '<div class="item-top"><span class="fam">' + esc(it.family) + ' · ' + esc(it.family_title) +
    '</span>' + badge(it.verdict) + '</div>' +
    '<h2>' + esc(it.name) + '</h2>' +
    '<div class="card-id">' + esc(it.id) + '</div></div>';

  FIELD_ORDER.forEach(function (k) {
    if (!it.fields[k]) return;
    var cls = k === 'proverka' ? 'field field-check' : 'field';
    html += '<div class="' + cls + '"><span class="field-label">' + esc(FIELD_LABEL[k] || k) +
      '</span><div class="field-value">' + it.fields[k] + '</div></div>';
  });
  Object.keys(it.fields).forEach(function (k) {
    if (FIELD_ORDER.indexOf(k) !== -1 || FIELD_HIDDEN[k]) return;
    html += '<div class="field"><span class="field-label">' + esc(k) +
      '</span><div class="field-value">' + it.fields[k] + '</div></div>';
  });
  if (it.notes) html += '<div class="note prose">' + it.notes + '</div>';
  html += '<div class="field"><span class="field-label">Семья</span><div class="field-value">' +
    '<a href="#/family/' + encodeURIComponent(it.family) + '">Все идеи семьи ' + esc(it.family) +
    ' — ' + esc(it.family_title) + '</a></div></div>';
  app.innerHTML = html;
  window.scrollTo(0, 0);
}

function viewFamilies() {
  setTitle('Семьи', false);
  markTab('families');
  searchRow.hidden = true;
  chipsEl.innerHTML = '';
  var html = '<p class="count">23 семьи таксономии, 26 файлов: три самые широкие разбиты пополам</p>';
  html += DATA.families.map(function (f) {
    return '<a class="item" href="#/family/' + encodeURIComponent(f.code) + '">' +
      '<div class="item-top"><span class="fam">' + esc(f.code) + '</span>' +
      '<span class="fam">' + f.count + ' идей</span></div>' +
      '<div class="item-name">' + esc(f.title) + '</div></a>';
  }).join('');
  app.innerHTML = html;
  window.scrollTo(0, 0);
}

function viewFamily(code) {
  var f = null;
  for (var i = 0; i < DATA.families.length; i++) if (DATA.families[i].code === code) { f = DATA.families[i]; break; }
  if (!f) { app.innerHTML = '<p class="empty">Семья не найдена.</p>'; return; }
  setTitle('Семья ' + code, true);
  markTab('families');
  searchRow.hidden = true;
  chipsEl.innerHTML = '';
  var ideas = DATA.ideas.filter(function (it) { return it.family === code; });
  var head = '<div class="card-head"><span class="fam">' + esc(code) + '</span>' +
    '<h2>' + esc(f.title) + '</h2></div>' +
    '<p class="count">' + ideas.length + ' идей</p>' + ideas.map(itemHtml).join('');
  app.innerHTML = head + '<p class="loading">Загрузка обзора слоя…</p>';
  window.scrollTo(0, 0);
  loadFamily(code).then(function (d) {
    if (location.hash.indexOf(code) === -1) return;
    var tail = '';
    if (d.intro) tail += '<div class="note prose"><h2>Обзор слоя</h2>' + d.intro + '</div>';
    if (d.appendix) tail += '<div class="note prose">' + d.appendix + '</div>';
    app.innerHTML = head + tail;
  }).catch(function () { app.innerHTML = head; });
}

function viewDocs() {
  setTitle('Разборы', false);
  markTab('docs');
  searchRow.hidden = true;
  chipsEl.innerHTML = '';
  app.innerHTML = '<p class="count">Сводные разделы исследования</p>' + docsIndex.map(function (d) {
    return '<a class="item" href="#/doc/' + encodeURIComponent(d.slug) + '">' +
      '<div class="item-name">' + esc(d.title) + '</div></a>';
  }).join('');
  window.scrollTo(0, 0);
}

function viewDoc(slug) {
  var meta = null;
  for (var i = 0; i < docsIndex.length; i++) if (docsIndex[i].slug === slug) { meta = docsIndex[i]; break; }
  setTitle(meta ? meta.title : 'Документ', true);
  markTab('docs');
  searchRow.hidden = true;
  chipsEl.innerHTML = '';
  if (docCache[slug]) { app.innerHTML = '<div class="prose">' + docCache[slug].html + '</div>'; window.scrollTo(0, 0); return; }
  app.innerHTML = '<p class="loading">Загрузка…</p>';
  fetch('data/' + slug + '.json').then(function (r) { return r.json(); }).then(function (d) {
    docCache[slug] = d;
    if (location.hash.indexOf(slug) !== -1) {
      app.innerHTML = '<div class="prose">' + d.html + '</div>';
      window.scrollTo(0, 0);
    }
  }).catch(function () { app.innerHTML = '<p class="empty">Не удалось загрузить раздел.</p>'; });
}

function viewAbout() {
  setTitle('О работе', false);
  markTab('about');
  searchRow.hidden = true;
  chipsEl.innerHTML = '';
  var c = DATA.counts;
  app.innerHTML = '<div class="prose">' +
    '<p>Каталог бизнесов, построенных на ИИ и вокруг ИИ, по состоянию на 8 августа 2026, ' +
    'с проверкой того, есть ли у каждой идеи российский аналог. Данные собраны многоагентным ' +
    'прогоном: агент на каждую семью таксономии, затем скептик на каждую семью с обратной ' +
    'задачей — опровергнуть найденное.</p>' +
    '<p><strong>' + DATA.total + ' идей</strong> в 23 семьях. По России: ' +
    'свободно ' + (c['свободно'] || 0) + ', частично ' + (c['частично'] || 0) +
    ', занято ' + (c['занято'] || 0) + ', без данных ' + (c['нет данных'] || 0) + '.</p>' +
    '<h2>Как читать вердикт по России</h2>' +
    '<p>«Свободно» здесь означает «аналог не найден», а не «его нет». Скептики проверили ' +
    '138 таких вердиктов и изменили 133 — всегда в сторону «занято». Прежде чем опираться ' +
    'на вердикт, откройте раздел «Проверка скептиков»: там перечислено, что именно ' +
    'опровергнуто и чем.</p>' +
    '<h2>Чего в данных нет</h2>' +
    '<p>Не выполнены четыре сквозных прохода по российским каналам — сторы приложений, ' +
    'vc.ru и Habr, корпоративный контур CNews и TAdviser, каталоги телеграм-ботов и VK. ' +
    'Не выполнены три отдельные охоты за провалами: сводный раздел собран из семейных файлов. ' +
    'Семь семей не получили скептика. Подробности — в разделе «Что не проверено».</p>' +
    '<h2>Цифры</h2>' +
    '<p>Финансовые показатели западных игроков — в основном сторонние оценки, расходящиеся ' +
    'между собой. Дата рядом с цифрой означает день снятия данных.</p>' +
    '</div>';
  window.scrollTo(0, 0);
}

/* ---------------------------------------------------------------- маршруты */

function route() {
  if (!DATA) return;
  var h = location.hash.replace(/^#/, '') || '/';
  var parts = h.split('/').filter(Boolean);
  if (!parts.length) return viewIdeas();
  if (parts[0] === 'idea') return viewIdea(decodeURIComponent(parts[1] || ''));
  if (parts[0] === 'families') return viewFamilies();
  if (parts[0] === 'family') return viewFamily(decodeURIComponent(parts[1] || ''));
  if (parts[0] === 'docs') return viewDocs();
  if (parts[0] === 'doc') return viewDoc(decodeURIComponent(parts[1] || ''));
  if (parts[0] === 'about') return viewAbout();
  return viewIdeas();
}

var timer = null;
qEl.addEventListener('input', function () {
  clearTimeout(timer);
  timer = setTimeout(function () {
    state.q = qEl.value;
    state.shown = PAGE;
    if (location.hash.replace(/^#/, '').replace(/^\//, '')) go('#/');
    else viewIdeas();
  }, 150);
});

backEl.onclick = function () {
  if (history.length > 1) history.back();
  else go('#/');
};

window.addEventListener('hashchange', route);

Promise.all([
  fetch('data/list.json').then(function (r) { return r.json(); }),
  fetch('data/docs.json').then(function (r) { return r.json(); }).catch(function () { return []; })
]).then(function (res) {
  DATA = res[0];
  docsIndex = res[1] || [];
  route();
}).catch(function (e) {
  app.innerHTML = '<p class="empty">Не удалось загрузить данные каталога.<br>' + esc(e.message) + '</p>';
});
