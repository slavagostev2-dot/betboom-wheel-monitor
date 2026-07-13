'use strict';

const VERSION='3.0.0';
const REPO='slavagostev2-dot/betboom-wheel-monitor';
const ORIGINS=[
  `https://raw.githubusercontent.com/${REPO}/main/`,
  `https://cdn.jsdelivr.net/gh/${REPO}@main/`
];
const tg=window.Telegram?.WebApp||null;
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const app={
  route:'home',days:7,sourceMode:'primary',query:'',loading:false,lastSync:null,
  data:{state:{},stats:{daily:{},sources:{}},primary:[],nightly:[]},
  joined:new Set(),settings:{autoRefresh:true,haptics:true}
};

const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const date=v=>{if(!v)return null;const d=new Date(v);return Number.isNaN(+d)?null:d};
const num=v=>new Intl.NumberFormat('ru-RU').format(Number(v||0));
const compact=v=>new Intl.NumberFormat('ru-RU',{notation:'compact',maximumFractionDigits:1}).format(Number(v||0));
const parseList=t=>[...new Map(String(t||'').split(/\r?\n/).map(x=>x.split('#')[0].trim().replace(/^@/,'')).filter(Boolean).map(x=>[x.toLowerCase(),x])).values()];
const safeUrl=v=>{try{const u=new URL(String(v||''));return /^https?:$/.test(u.protocol)?u.toString():''}catch{return''}};
const left=v=>{const d=v instanceof Date?v:date(v);if(!d)return'Время не определено';const s=Math.floor((+d-Date.now())/1000);if(s<=0)return'Время наступило';const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;return h?`${h} ч. ${m} мин.`:m?`${m} мин. ${String(sec).padStart(2,'0')} сек.`:`${sec} сек.`};
const user=()=>tg?.initDataUnsafe?.user||null;

let toastTimer;
function toast(text){const el=$('#toast');el.textContent=text;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),2300)}
function haptic(type='light'){if(!app.settings.haptics||!tg?.HapticFeedback)return;try{['success','warning','error'].includes(type)?tg.HapticFeedback.notificationOccurred(type):tg.HapticFeedback.impactOccurred(type)}catch{}}

const store={
  localGet(key,fallback){try{const raw=localStorage.getItem(`bb:${key}`);return raw?JSON.parse(raw):fallback}catch{return fallback}},
  get(key,fallback){return new Promise(resolve=>{if(tg?.CloudStorage?.getItem){tg.CloudStorage.getItem(key,(err,value)=>{if(!err&&value){try{return resolve(JSON.parse(value))}catch{}}resolve(this.localGet(key,fallback))})}else resolve(this.localGet(key,fallback))})},
  set(key,value){const raw=JSON.stringify(value);try{localStorage.setItem(`bb:${key}`,raw)}catch{};if(tg?.CloudStorage?.setItem)tg.CloudStorage.setItem(key,raw,()=>{})}
};

function setupTelegram(){
  if(!tg)return;
  try{
    tg.ready();tg.expand();
    tg.setHeaderColor?.('#090a0d');
    tg.setBackgroundColor?.('#090a0d');
    tg.setBottomBarColor?.('#0d0e12');
  }catch(error){console.warn(error)}
}

async function loadUser(){
  const [joined,settings]=await Promise.all([
    store.get('joined',[]),
    store.get('settings',app.settings)
  ]);
  app.joined=new Set(Array.isArray(joined)?joined.map(x=>String(x).toLowerCase()):[]);
  app.settings={autoRefresh:settings?.autoRefresh!==false,haptics:settings?.haptics!==false};
}

async function fetchOne(path,type='json'){
  let lastError;
  for(const base of ORIGINS){
    const ctl=new AbortController();
    const timer=setTimeout(()=>ctl.abort(),12000);
    try{
      const response=await fetch(`${base}${path}?t=${Date.now()}`,{cache:'no-store',signal:ctl.signal});
      clearTimeout(timer);
      if(!response.ok)throw new Error(`${path}: ${response.status}`);
      return type==='text'?response.text():response.json();
    }catch(error){clearTimeout(timer);lastError=error}
  }
  throw lastError||new Error(`Не удалось загрузить ${path}`);
}

async function loadData(quiet=false){
  if(app.loading)return;
  app.loading=true;
  $('#refreshButton').classList.add('loading');
  try{
    const [state,stats,primaryText,nightlyText]=await Promise.all([
      fetchOne('state.json'),fetchOne('source_stats.json'),fetchOne('public_sources.txt','text'),fetchOne('source_catalog.txt','text')
    ]);
    app.data={state,stats,primary:parseList(primaryText),nightly:parseList(nightlyText)};
    app.lastSync=new Date();
    renderAll();
    if(!quiet){toast('Данные обновлены');haptic('success')}
  }catch(error){
    console.error(error);
    toast('Не удалось обновить данные');
    haptic('error');
    if(!app.lastSync)renderFatal();
  }finally{
    app.loading=false;
    $('#refreshButton').classList.remove('loading');
    $('#app').hidden=false;
    requestAnimationFrame(()=>$('#splash').classList.add('hidden'));
  }
}

function activeWheels(){
  return Object.entries(app.data.state?.active_wheels||{})
    .filter(([,x])=>x&&typeof x==='object')
    .map(([key,x])=>({...x,key,identifier:String(x.identifier||key),deadlineObj:date(x.deadline||x.deadline_at||x.spin_at)}))
    .filter(x=>!x.deadlineObj||x.deadlineObj>Date.now()-5*60*1000)
    .sort((a,b)=>(+a.deadlineObj||Infinity)-(+b.deadlineObj||Infinity));
}
const wheelKey=x=>String(x?.identifier||x?.key||'').toLowerCase();
const joined=x=>app.joined.has(typeof x==='string'?x.toLowerCase():wheelKey(x));

async function toggleJoined(id){
  const key=String(id||'').toLowerCase();
  if(!key)return;
  if(app.joined.has(key)){app.joined.delete(key);toast('Отметка участия снята')}
  else{app.joined.add(key);toast('Участие отмечено');haptic('success')}
  store.set('joined',[...app.joined]);
  renderHome();renderProfile();
}

function totals(days){
  const out={},allowed=new Set();
  for(let i=0;i<days;i++){
    const d=new Date();d.setDate(d.getDate()-i);
    allowed.add(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`);
  }
  for(const [day,row] of Object.entries(app.data.stats?.daily||{})){
    if(!allowed.has(day)||!row?.totals)continue;
    for(const [name,value] of Object.entries(row.totals))if(typeof value==='number')out[name]=(out[name]||0)+value;
  }
  return out;
}
function sourceStats(name){const key=Object.keys(app.data.stats?.sources||{}).find(x=>x.toLowerCase()===String(name).toLowerCase());return key?app.data.stats.sources[key]:{}}
function ranking(){
  return Object.entries(app.data.stats?.sources||{})
    .map(([source,row])=>({source,wheels:Number(row?.wheel_posts||0),activations:Number(row?.activation_sent||0)}))
    .filter(x=>x.wheels>0)
    .sort((a,b)=>b.wheels-a.wheels||b.activations-a.activations||a.source.localeCompare(b.source));
}

function wheelCard(x){
  const id=wheelKey(x),mine=joined(x),url=safeUrl(x.url),source=String(x.source||'неизвестно');
  return `<article class="card wheel-card">
    <div class="wheel-top">
      <div class="wheel-id"><small>Колесо</small><h3>${esc(x.identifier||x.key)}</h3></div>
      <span class="badge ${mine?'mine':''}">${mine?'Участие отмечено':'Действует'}</span>
    </div>
    <div class="countdown" ${x.deadlineObj?`data-deadline="${esc(x.deadlineObj.toISOString())}"`:''}>${esc(x.deadlineObj?left(x.deadlineObj):'Время не определено')}</div>
    <div class="wheel-meta"><span>Источник</span><strong>@${esc(source)}</strong></div>
    <div class="actions">
      ${url?`<button class="button primary" data-action="open-url" data-url="${esc(url)}">Открыть колесо</button>`:'<button class="button primary" disabled>Ссылка недоступна</button>'}
      <button class="button ${mine?'success':'secondary'}" data-action="join" data-id="${esc(id)}">${mine?'Снять отметку':'Я участвую'}</button>
    </div>
  </article>`;
}

function renderHome(){
  const wheels=activeWheels();
  const mine=wheels.filter(joined).length;
  $('#page-home').innerHTML=`
    <h1 class="page-title">Главная</h1>
    <p class="page-subtitle">Все актуальные колёса в одном месте</p>
    <div class="metrics">
      <article class="metric"><strong>${wheels.length}</strong><span>Действующих колёс</span></article>
      <article class="metric"><strong>${mine}</strong><span>Моих отметок</span></article>
    </div>
    <section class="section">
      <h2 class="section-title">Актуальные колёса</h2>
      <div>${wheels.map(wheelCard).join('')||'<div class="empty">Сейчас действующих колёс нет.</div>'}</div>
    </section>`;
}

function chart(days){
  const count=days===30?14:Math.max(1,days),rows=[];
  for(let i=count-1;i>=0;i--){
    const d=new Date();d.setDate(d.getDate()-i);
    const key=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    rows.push({date:d,value:Number(app.data.stats?.daily?.[key]?.totals?.checks||0)});
  }
  const max=Math.max(1,...rows.map(x=>x.value));
  return `<div class="chart">${rows.map(x=>`<div class="bar-col"><div class="bar-wrap"><i class="bar" style="height:${Math.max(x.value?5:2,Math.round(x.value/max*100))}%"></i></div><span class="bar-label">${x.date.toLocaleDateString('ru-RU',{day:'2-digit',month:'2-digit'})}</span></div>`).join('')}</div>`;
}
function rankRow(x,index){return `<button class="rank-row" type="button" data-action="source-info" data-source="${esc(x.source)}"><span class="rank-num">${index+1}</span><span class="row-copy"><strong>@${esc(x.source)}</strong><small>Подтверждённых активаций: ${num(x.activations)}</small></span><span class="row-value">${num(x.wheels)}</span></button>`}

function renderStats(){
  const t=totals(app.days);
  $('#page-stats').innerHTML=`
    <h1 class="page-title">Статистика</h1>
    <p class="page-subtitle">Результаты работы монитора</p>
    <div class="periods">${[1,7,30].map(x=>`<button class="chip ${app.days===x?'active':''}" type="button" data-days="${x}">${x===1?'Сегодня':`${x} дней`}</button>`).join('')}</div>
    <div class="stats-grid">
      <article class="metric"><strong>${compact(t.checks)}</strong><span>Проверок источников</span></article>
      <article class="metric"><strong>${compact(t.messages_scanned)}</strong><span>Просмотрено сообщений</span></article>
      <article class="metric"><strong>${num(t.wheel_posts)}</strong><span>Постов с колёсами</span></article>
      <article class="metric"><strong>${num(t.activation_sent)}</strong><span>Активных подтверждено</span></article>
    </div>
    <section class="section"><article class="card"><h2 class="section-title">Проверки по дням</h2>${chart(app.days)}</article></section>
    <section class="section"><h2 class="section-title">Рейтинг источников</h2><article class="card">${ranking().slice(0,15).map(rankRow).join('')||'<div class="empty">Рейтинг ещё формируется.</div>'}</article></section>`;
}

function filteredSources(){
  const list=app.sourceMode==='nightly'?app.data.nightly:app.data.primary;
  const q=app.query.trim().toLowerCase();
  return q?list.filter(x=>x.toLowerCase().includes(q)):list;
}
function sourceRow(name){
  const stats=sourceStats(name),wheels=Number(stats?.wheel_posts||0);
  return `<button class="source-row" type="button" data-action="source-info" data-source="${esc(name)}"><span class="row-copy"><strong>@${esc(name)}</strong><small>${wheels?`Найдено колёс: ${num(wheels)}`:'Открыть информацию'}</small></span><span class="row-value">›</span></button>`;
}
function renderSources(){
  const rows=filteredSources();
  $('#page-sources').innerHTML=`
    <h1 class="page-title">Источники</h1>
    <p class="page-subtitle">Каналы, которые проверяет монитор</p>
    <form id="sourceRequestForm" class="source-form">
      <h2>Предложить источник</h2>
      <p>Бот проверит публичность канала и последние сообщения. Администратор получит запрос с результатом проверки.</p>
      <div class="form-row"><input id="sourceRequestInput" class="input" type="text" inputmode="text" autocomplete="off" maxlength="33" placeholder="username канала"><button class="form-button" type="submit">Отправить</button></div>
    </form>
    <div class="tabs section"><button class="chip ${app.sourceMode==='primary'?'active':''}" type="button" data-source-mode="primary">Основные ${app.data.primary.length}</button><button class="chip ${app.sourceMode==='nightly'?'active':''}" type="button" data-source-mode="nightly">Ночное наблюдение ${app.data.nightly.length}</button></div>
    <input id="sourceSearch" class="search" type="search" autocomplete="off" placeholder="Поиск по username" value="${esc(app.query)}">
    <article class="card">${rows.slice(0,100).map(sourceRow).join('')||'<div class="empty">Источники не найдены.</div>'}</article>`;
}

function renderProfile(){
  const u=user(),name=u?[u.first_name,u.last_name].filter(Boolean).join(' '):'Пользователь';
  const photo=safeUrl(u?.photo_url)||'icon.svg';
  const mine=activeWheels().filter(joined);
  $('#page-profile').innerHTML=`
    <h1 class="page-title">Профиль</h1>
    <article class="card profile-head"><img src="${esc(photo)}" alt=""><div class="profile-copy"><strong>${esc(name||'Пользователь')}</strong><span>${u?.username?`@${esc(u.username)}`:'Telegram Mini App'}</span></div></article>
    <section class="section"><h2 class="section-title">Мои отметки</h2><div>${mine.map(wheelCard).join('')||'<div class="empty">Вы пока не отметили участие в действующих колёсах.</div>'}</div></section>
    <section class="section"><h2 class="section-title">Настройки</h2><article class="card">
      <div class="setting"><div class="setting-copy"><strong>Автообновление</strong><small>Обновлять данные раз в минуту</small></div><button class="switch ${app.settings.autoRefresh?'on':''}" type="button" data-setting="autoRefresh" aria-label="Автообновление"></button></div>
      <div class="setting"><div class="setting-copy"><strong>Тактильный отклик</strong><small>Подтверждать действия вибрацией</small></div><button class="switch ${app.settings.haptics?'on':''}" type="button" data-setting="haptics" aria-label="Тактильный отклик"></button></div>
      <div class="setting"><div class="setting-copy"><strong>Версия приложения</strong><small>BetBoom Monitor</small></div><span class="muted">${VERSION}</span></div>
    </article></section>`;
}

function renderAll(){renderHome();renderStats();renderSources();renderProfile();updateTimers()}
function route(name){
  if(!['home','stats','sources','profile'].includes(name))name='home';
  app.route=name;
  $$('.page').forEach(x=>x.classList.toggle('active',x.dataset.page===name));
  $$('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.route===name));
  $('#headerSubtitle').textContent={home:'Актуальные колёса',stats:'Статистика',sources:'Источники',profile:'Профиль'}[name];
  window.scrollTo({top:0,behavior:'smooth'});
}
function updateTimers(){$$('[data-deadline]').forEach(el=>el.textContent=left(el.dataset.deadline))}

function openUrl(url){
  const safe=safeUrl(url);if(!safe)return;
  try{safe.includes('t.me/')?tg?.openTelegramLink?.(safe):tg?.openLink?.(safe,{try_instant_view:false})}catch{}
  if(!tg)window.open(safe,'_blank','noopener');
}

function botUsername(){
  const params=new URLSearchParams(location.search);
  const fromQuery=(params.get('bot')||'').replace(/^@/,'');
  const fromConfig=String(window.BB_CONFIG?.botUsername||'').replace(/^@/,'');
  const value=fromQuery||fromConfig||localStorage.getItem('bb:botUsername')||'';
  if(value)try{localStorage.setItem('bb:botUsername',value)}catch{}
  return value;
}
function normalizeSource(value){return String(value||'').trim().replace(/^https?:\/\/t\.me\//i,'').replace(/^@/,'').split(/[/?#]/)[0]}
function knownSource(username){const key=username.toLowerCase();return app.data.primary.some(x=>x.toLowerCase()===key)||app.data.nightly.some(x=>x.toLowerCase()===key)}
async function submitSourceRequest(raw){
  const username=normalizeSource(raw);
  if(!/^[A-Za-z][A-Za-z0-9_]{3,31}$/.test(username)){toast('Введите корректный username канала');haptic('warning');return}
  if(knownSource(username)){toast('Этот источник уже проверяется');return}
  const bot=botUsername();
  if(bot){
    const link=`https://t.me/${encodeURIComponent(bot)}?start=source_${encodeURIComponent(username)}`;
    toast('Открываю запрос в боте');haptic('success');
    try{tg?.openTelegramLink?.(link)}catch{}
    if(!tg)window.open(link,'_blank','noopener');
    return;
  }
  if(tg?.sendData){
    try{tg.sendData(JSON.stringify({type:'source_request',source:username,version:1}));return}catch(error){console.warn(error)}
  }
  const command=`/source ${username}`;
  try{await navigator.clipboard.writeText(command);toast('Команда скопирована. Отправьте её боту.')}catch{showDialog(`<h2>Отправьте запрос боту</h2><p>Скопируйте и отправьте эту команду в чат с ботом:</p><div class="card"><strong>${esc(command)}</strong></div>`)}
}

function showSourceInfo(source){
  const mode=app.data.primary.some(x=>x.toLowerCase()===source.toLowerCase())?'Основная проверка':'Ночное наблюдение';
  const stats=sourceStats(source),wheels=Number(stats?.wheel_posts||0),acts=Number(stats?.activation_sent||0);
  showDialog(`<h2>@${esc(source)}</h2><p>${esc(mode)}</p><article class="card"><div class="setting"><div class="setting-copy"><strong>Постов с колёсами</strong><small>За всё накопленное время</small></div><span class="row-value">${num(wheels)}</span></div><div class="setting"><div class="setting-copy"><strong>Подтверждённых активаций</strong><small>Успешно подтверждено монитором</small></div><span class="row-value">${num(acts)}</span></div></article><div class="actions"><button class="button primary" data-action="open-url" data-url="https://t.me/${esc(source)}">Открыть Telegram</button><button class="button secondary" data-action="close-dialog">Закрыть</button></div>`)
}
function showDialog(html){const dialog=$('#dialog');$('#dialogBody').innerHTML=html;dialog.showModal?.()}
function closeDialog(){$('#dialog').close?.()}
function renderFatal(){$('#page-home').innerHTML='<div class="empty">Не удалось загрузить данные. Нажмите кнопку обновления.</div>';route('home')}

function bindEvents(){
  document.addEventListener('click',event=>{
    const routeButton=event.target.closest('[data-route]');if(routeButton){route(routeButton.dataset.route);return}
    const actionButton=event.target.closest('[data-action]');if(actionButton){
      const action=actionButton.dataset.action;
      if(action==='join')toggleJoined(actionButton.dataset.id);
      else if(action==='open-url')openUrl(actionButton.dataset.url);
      else if(action==='source-info')showSourceInfo(actionButton.dataset.source);
      else if(action==='close-dialog')closeDialog();
      return;
    }
    const day=event.target.closest('[data-days]');if(day){app.days=Number(day.dataset.days)||7;renderStats();return}
    const mode=event.target.closest('[data-source-mode]');if(mode){app.sourceMode=mode.dataset.sourceMode;renderSources();return}
    const setting=event.target.closest('[data-setting]');if(setting){const key=setting.dataset.setting;app.settings[key]=!app.settings[key];store.set('settings',app.settings);renderProfile();haptic('light')}
  });
  document.addEventListener('submit',event=>{if(event.target.id==='sourceRequestForm'){event.preventDefault();submitSourceRequest($('#sourceRequestInput').value)}});
  document.addEventListener('input',event=>{if(event.target.id==='sourceSearch'){app.query=event.target.value;const card=event.target.nextElementSibling;card.innerHTML=filteredSources().slice(0,100).map(sourceRow).join('')||'<div class="empty">Источники не найдены.</div>'}});
  $('#refreshButton').addEventListener('click',()=>loadData(false));
  $('#dialog').addEventListener('click',event=>{if(event.target===$('#dialog'))closeDialog()});
}

async function init(){
  setupTelegram();bindEvents();await loadUser();await loadData(true);route('home');
  setInterval(updateTimers,1000);
  setInterval(()=>{if(app.settings.autoRefresh&&document.visibilityState==='visible')loadData(true)},60000);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&app.settings.autoRefresh)loadData(true)});
  if('serviceWorker'in navigator)navigator.serviceWorker.register('./service-worker.js').catch(console.warn);
}
init();
