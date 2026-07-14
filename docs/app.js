'use strict';

const VERSION='5.1.0';
const BRAND='BB V.G.';
const REPO='slavagostev2-dot/betboom-wheel-monitor';
const ORIGINS=[
  `https://raw.githubusercontent.com/${REPO}/main/`,
  `https://cdn.jsdelivr.net/gh/${REPO}@main/`
];
const tg=window.Telegram?.WebApp||null;
const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];
const app={
  route:'home',
  days:7,
  sourceMode:'primary',
  query:'',
  loading:false,
  lastSync:null,
  data:{state:{},stats:{daily:{},sources:{}},primary:[],nightly:[]},
  joined:new Set(),
  settings:{autoRefresh:true,haptics:true,lightTheme:false}
};

const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({
  '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'
}[char]));
const date=value=>{if(!value)return null;const parsed=new Date(value);return Number.isNaN(+parsed)?null:parsed};
const num=value=>new Intl.NumberFormat('ru-RU').format(Number(value||0));
const compact=value=>new Intl.NumberFormat('ru-RU',{notation:'compact',maximumFractionDigits:1}).format(Number(value||0));
const parseList=text=>[...new Map(String(text||'').split(/\r?\n/).map(line=>line.split('#')[0].trim().replace(/^@/,'')).filter(Boolean).map(item=>[item.toLowerCase(),item])).values()];
const safeUrl=value=>{try{const url=new URL(String(value||''));return /^https?:$/.test(url.protocol)?url.toString():''}catch{return''}};
const initials=value=>String(value||'BB').replace(/^@/,'').slice(0,2).toUpperCase();
const timeLeft=value=>{
  const deadline=value instanceof Date?value:date(value);
  if(!deadline)return'Время не определено';
  const seconds=Math.floor((+deadline-Date.now())/1000);
  if(seconds<=0)return'Время наступило';
  const hours=Math.floor(seconds/3600);
  const minutes=Math.floor((seconds%3600)/60);
  const rest=seconds%60;
  if(hours)return`${hours} ч. ${String(minutes).padStart(2,'0')} мин.`;
  if(minutes)return`${minutes} мин. ${String(rest).padStart(2,'0')} сек.`;
  return`${rest} сек.`;
};
const currentUser=()=>tg?.initDataUnsafe?.user||null;

let toastTimer;
function toast(text){
  const element=$('#toast');
  element.textContent=text;
  element.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>element.classList.remove('show'),2300);
}
function haptic(type='light'){
  if(!app.settings.haptics||!tg?.HapticFeedback)return;
  try{
    if(type==='selection')tg.HapticFeedback.selectionChanged?.();
    else if(['success','warning','error'].includes(type))tg.HapticFeedback.notificationOccurred?.(type);
    else tg.HapticFeedback.impactOccurred?.(type);
  }catch{}
}

const THEME_COLORS={
  dark:{header:'#08080c',background:'#08080c',bottom:'#0c0b11'},
  light:{header:'#f8f5fb',background:'#f4f1f8',bottom:'#faf8fc'}
};
function applyTheme(){
  const light=app.settings.lightTheme===true;
  const theme=light?'light':'dark';
  const colors=THEME_COLORS[theme];
  const root=document.documentElement;
  root.dataset.theme=theme;
  root.classList.toggle('light-theme',light);
  root.style.colorScheme=theme;
  $('#app')?.classList.toggle('light-theme',light);
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content',colors.background);
  try{
    tg?.setHeaderColor?.(colors.header);
    tg?.setBackgroundColor?.(colors.background);
    tg?.setBottomBarColor?.(colors.bottom);
  }catch(error){console.warn('Telegram theme:',error)}
}

const store={
  localGet(key,fallback){try{const raw=localStorage.getItem(`bbvg:${key}`);return raw?JSON.parse(raw):fallback}catch{return fallback}},
  get(key,fallback){
    return new Promise(resolve=>{
      if(tg?.CloudStorage?.getItem){
        tg.CloudStorage.getItem(key,(error,value)=>{
          if(!error&&value){try{return resolve(JSON.parse(value))}catch{}}
          resolve(this.localGet(key,fallback));
        });
      }else resolve(this.localGet(key,fallback));
    });
  },
  set(key,value){
    const raw=JSON.stringify(value);
    try{localStorage.setItem(`bbvg:${key}`,raw)}catch{}
    if(tg?.CloudStorage?.setItem)tg.CloudStorage.setItem(key,raw,()=>{});
  }
};

function setupTelegram(){
  if(!tg)return;
  try{
    tg.ready();
    tg.expand();
    tg.disableVerticalSwipes?.();
    applyTheme();
  }catch(error){console.warn(error)}
}

async function loadUser(){
  const [joined,settings]=await Promise.all([
    store.get('joined',[]),
    store.get('settings',app.settings)
  ]);
  app.joined=new Set(Array.isArray(joined)?joined.map(item=>String(item).toLowerCase()):[]);
  let legacyLightTheme=false;
  try{legacyLightTheme=localStorage.getItem('bbvg:appearance')==='light'}catch{}
  app.settings={
    autoRefresh:settings?.autoRefresh!==false,
    haptics:settings?.haptics!==false,
    lightTheme:typeof settings?.lightTheme==='boolean'?settings.lightTheme:legacyLightTheme
  };
  store.set('settings',app.settings);
  applyTheme();
}

async function fetchOne(path,type='json'){
  let lastError;
  for(const base of ORIGINS){
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),12000);
    try{
      const response=await fetch(`${base}${path}?t=${Date.now()}`,{cache:'no-store',signal:controller.signal});
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
      fetchOne('state.json'),
      fetchOne('source_stats.json'),
      fetchOne('public_sources.txt','text'),
      fetchOne('source_catalog.txt','text')
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
    .filter(([,value])=>value&&typeof value==='object')
    .map(([key,value])=>({
      ...value,
      key,
      identifier:String(value.identifier||key),
      deadlineObj:date(value.deadline||value.deadline_at||value.spin_at)
    }))
    .filter(item=>!item.deadlineObj||item.deadlineObj>Date.now()-5*60*1000)
    .sort((a,b)=>(+a.deadlineObj||Infinity)-(+b.deadlineObj||Infinity));
}
const wheelKey=wheel=>String(wheel?.identifier||wheel?.key||'').toLowerCase();
const isJoined=wheel=>app.joined.has(typeof wheel==='string'?wheel.toLowerCase():wheelKey(wheel));

async function toggleJoined(id){
  const key=String(id||'').toLowerCase();
  if(!key)return;
  if(app.joined.has(key)){
    app.joined.delete(key);
    toast('Отметка участия снята');
  }else{
    app.joined.add(key);
    toast('Участие отмечено');
    haptic('success');
  }
  store.set('joined',[...app.joined]);
  renderHome();
  renderProfile();
}

function totals(days){
  const result={};
  const allowed=new Set();
  for(let index=0;index<days;index++){
    const current=new Date();
    current.setDate(current.getDate()-index);
    allowed.add(`${current.getFullYear()}-${String(current.getMonth()+1).padStart(2,'0')}-${String(current.getDate()).padStart(2,'0')}`);
  }
  for(const [day,row] of Object.entries(app.data.stats?.daily||{})){
    if(!allowed.has(day)||!row?.totals)continue;
    for(const [name,value] of Object.entries(row.totals)){
      if(typeof value==='number')result[name]=(result[name]||0)+value;
    }
  }
  return result;
}
function sourceStats(name){
  const key=Object.keys(app.data.stats?.sources||{}).find(item=>item.toLowerCase()===String(name).toLowerCase());
  return key?app.data.stats.sources[key]:{};
}
function ranking(){
  return Object.entries(app.data.stats?.sources||{})
    .map(([source,row])=>({source,wheels:Number(row?.wheel_posts||0),activations:Number(row?.activation_sent||0)}))
    .filter(item=>item.wheels>0)
    .sort((a,b)=>b.wheels-a.wheels||b.activations-a.activations||a.source.localeCompare(b.source));
}

const iconSvg={
  wheel:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2"/><path d="M12 4v4m0 8v4M4 12h4m8 0h4M6.3 6.3l2.8 2.8m5.8 5.8 2.8 2.8m0-11.4-2.8 2.8m-5.8 5.8-2.8 2.8"/></svg>',
  check:'<svg viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/><circle cx="12" cy="12" r="9"/></svg>',
  scan:'<svg viewBox="0 0 24 24"><path d="M4 8V5a1 1 0 0 1 1-1h3m8 0h3a1 1 0 0 1 1 1v3m0 8v3a1 1 0 0 1-1 1h-3m-8 0H5a1 1 0 0 1-1-1v-3"/><path d="M8 12h8"/></svg>',
  message:'<svg viewBox="0 0 24 24"><path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-5 3V7a2 2 0 0 1 2-2z"/></svg>',
  link:'<svg viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.1-1.1"/></svg>'
};

function wheelCard(wheel){
  const id=wheelKey(wheel);
  const joined=isJoined(wheel);
  const url=safeUrl(wheel.url);
  const source=String(wheel.source||'неизвестно');
  return `<article class="card wheel-card ${joined?'joined':''}">
    <div class="wheel-top">
      <div class="wheel-main">
        <span class="wheel-avatar">BB</span>
        <div class="wheel-id"><h3>${esc(wheel.identifier||wheel.key)}</h3><small>@${esc(source)}</small></div>
      </div>
      <span class="badge ${joined?'mine':''}">${joined?'Отмечено':'Активно'}</span>
    </div>
    <div class="countdown-row"><span>До прокрутки</span><strong class="countdown" ${wheel.deadlineObj?`data-deadline="${esc(wheel.deadlineObj.toISOString())}"`:''}>${esc(wheel.deadlineObj?timeLeft(wheel.deadlineObj):'Время не определено')}</strong></div>
    <div class="wheel-meta"><span>Источник</span><strong>@${esc(source)}</strong></div>
    <div class="actions">
      ${url?`<button class="button primary" data-action="open-url" data-url="${esc(url)}">Открыть колесо</button>`:'<button class="button primary" disabled>Ссылка недоступна</button>'}
      <button class="button ${joined?'success':'secondary'}" data-action="join" data-id="${esc(id)}">${joined?'Снять отметку':'Я участвую'}</button>
    </div>
  </article>`;
}

function renderHome(){
  const wheels=activeWheels();
  const mine=wheels.filter(isJoined).length;
  $('#page-home').innerHTML=`
    <h1 class="page-title">Главная</h1>
    <p class="page-subtitle">Актуальные колёса и личные отметки</p>
    <article class="overview">
      <div class="overview-copy"><small>${BRAND}</small><strong>Монитор колёс и источников</strong></div>
      <div class="metrics">
        <article class="metric"><strong>${wheels.length}</strong><span>Действующих колёс</span></article>
        <article class="metric"><strong>${mine}</strong><span>Моих отметок</span></article>
      </div>
    </article>
    <section class="section">
      <div class="section-head"><h2 class="section-title">Активные колёса</h2><span class="count-pill">${wheels.length}</span></div>
      <div>${wheels.map(wheelCard).join('')||'<div class="empty">Сейчас действующих колёс нет.</div>'}</div>
    </section>`;
}

function chart(days){
  const count=days===30?14:Math.max(1,days);
  const rows=[];
  for(let index=count-1;index>=0;index--){
    const current=new Date();
    current.setDate(current.getDate()-index);
    const key=`${current.getFullYear()}-${String(current.getMonth()+1).padStart(2,'0')}-${String(current.getDate()).padStart(2,'0')}`;
    rows.push({date:current,value:Number(app.data.stats?.daily?.[key]?.totals?.checks||0)});
  }
  const max=Math.max(1,...rows.map(item=>item.value));
  return `<div class="chart">${rows.map(item=>`<div class="bar-col"><div class="bar-wrap"><i class="bar" style="height:${Math.max(item.value?5:2,Math.round(item.value/max*100))}%"></i></div><span class="bar-label">${item.date.toLocaleDateString('ru-RU',{day:'2-digit',month:'2-digit'})}</span></div>`).join('')}</div>`;
}
function rankRow(item,index){
  return `<button class="rank-row" type="button" data-action="source-info" data-source="${esc(item.source)}"><span class="rank-num">${index+1}</span><span class="source-mark">${esc(initials(item.source))}</span><span class="row-copy"><strong>@${esc(item.source)}</strong><small>Подтверждённых активаций: ${num(item.activations)}</small></span><span class="row-value">${num(item.wheels)}</span></button>`;
}
function metricCard(icon,value,label){
  return `<article class="metric"><span class="metric-icon">${icon}</span><strong>${value}</strong><span>${label}</span></article>`;
}

function renderStats(){
  const total=totals(app.days);
  $('#page-stats').innerHTML=`
    <h1 class="page-title">Статистика</h1>
    <p class="page-subtitle">Результаты работы ${BRAND}</p>
    <div class="periods">${[1,7,30].map(days=>`<button class="chip ${app.days===days?'active':''}" type="button" data-days="${days}">${days===1?'Сегодня':`${days} дней`}</button>`).join('')}</div>
    <div class="stats-grid">
      ${metricCard(iconSvg.scan,compact(total.checks),'Проверок источников')}
      ${metricCard(iconSvg.message,compact(total.messages_scanned),'Просмотрено сообщений')}
      ${metricCard(iconSvg.wheel,num(total.wheel_posts),'Постов с колёсами')}
      ${metricCard(iconSvg.check,num(total.activation_sent),'Активных подтверждено')}
    </div>
    <section class="section"><article class="card"><div class="section-head"><h2 class="section-title">Активность</h2><span class="muted">${app.days===1?'Сегодня':`${app.days} дней`}</span></div>${chart(app.days)}</article></section>
    <section class="section"><div class="section-head"><h2 class="section-title">Топ источников</h2></div><article class="card">${ranking().slice(0,15).map(rankRow).join('')||'<div class="empty">Рейтинг ещё формируется.</div>'}</article></section>`;
}

function filteredSources(){
  const list=app.sourceMode==='nightly'?app.data.nightly:app.data.primary;
  const query=app.query.trim().toLowerCase();
  return query?list.filter(item=>item.toLowerCase().includes(query)):list;
}
function sourceRow(name){
  const stats=sourceStats(name);
  const wheels=Number(stats?.wheel_posts||0);
  return `<button class="source-row" type="button" data-action="source-info" data-source="${esc(name)}"><span class="source-mark">${esc(initials(name))}</span><span class="row-copy"><strong>@${esc(name)}</strong><small>${wheels?`Постов с колёсами: ${num(wheels)}`:'Статистика ещё формируется'}</small></span><span class="source-status">Активен</span></button>`;
}
function renderSources(){
  const rows=filteredSources();
  $('#page-sources').innerHTML=`
    <h1 class="page-title">Источники</h1>
    <p class="page-subtitle">Каналы, которые проверяет ${BRAND}</p>
    <form id="sourceRequestForm" class="source-form">
      <div class="source-form-head"><span class="source-form-icon">${iconSvg.link}</span><h2>Предложить источник</h2></div>
      <p>Отправьте username публичного канала. Бот проверит его, а администратор выберет основную или ночную проверку.</p>
      <div class="form-row"><input id="sourceRequestInput" class="input" type="text" inputmode="text" autocomplete="off" maxlength="33" placeholder="username канала"><button class="form-button" type="submit">Отправить</button></div>
    </form>
    <div class="tabs section"><button class="chip ${app.sourceMode==='primary'?'active':''}" type="button" data-source-mode="primary">Основные ${app.data.primary.length}</button><button class="chip ${app.sourceMode==='nightly'?'active':''}" type="button" data-source-mode="nightly">Ночное наблюдение ${app.data.nightly.length}</button></div>
    <input id="sourceSearch" class="search" type="search" autocomplete="off" placeholder="Поиск по username" value="${esc(app.query)}">
    <article class="card">${rows.slice(0,100).map(sourceRow).join('')||'<div class="empty">Источники не найдены.</div>'}</article>`;
}

function renderProfile(){
  const user=currentUser();
  const name=user?[user.first_name,user.last_name].filter(Boolean).join(' '):'Пользователь';
  const photo=safeUrl(user?.photo_url)||'icon.svg';
  const mine=activeWheels().filter(isJoined);
  $('#page-profile').innerHTML=`
    <h1 class="page-title">Профиль</h1>
    <p class="page-subtitle">Личные отметки и настройки</p>
    <article class="card profile-head"><img src="${esc(photo)}" alt=""><div class="profile-copy"><strong>${esc(name||'Пользователь')}</strong><span>${user?.username?`@${esc(user.username)}`:'Telegram Mini App'}</span></div></article>
    <section class="section"><div class="section-head"><h2 class="section-title">Мои отметки</h2><span class="count-pill">${mine.length}</span></div><div>${mine.map(wheelCard).join('')||'<div class="empty">Вы пока не отметили участие в действующих колёсах.</div>'}</div></section>
    <section class="section"><div class="section-head"><h2 class="section-title">Настройки</h2></div><article class="card">
      <div class="setting"><div class="setting-copy"><strong>Автообновление</strong><small>Обновлять данные раз в минуту</small></div><button class="switch ${app.settings.autoRefresh?'on':''}" type="button" data-setting="autoRefresh" aria-label="Автообновление"></button></div>
      <div class="setting"><div class="setting-copy"><strong>Тактильный отклик</strong><small>Подтверждать действия вибрацией</small></div><button class="switch ${app.settings.haptics?'on':''}" type="button" data-setting="haptics" aria-label="Тактильный отклик"></button></div>
      <div class="setting"><div class="setting-copy"><strong>Светлая тема</strong><small>Светлый фон и тёмный текст</small></div><button class="switch ${app.settings.lightTheme?'on':''}" type="button" data-setting="lightTheme" aria-label="Светлая тема" aria-pressed="${app.settings.lightTheme}"></button></div>
      <div class="setting"><div class="setting-copy"><strong>Версия приложения</strong><small>${BRAND}</small></div><span class="muted">${VERSION}</span></div>
    </article></section>`;
}

function renderAll(){renderHome();renderStats();renderSources();renderProfile();updateTimers()}
function route(name){
  if(!['home','stats','sources','profile'].includes(name))name='home';
  app.route=name;
  $$('.page').forEach(page=>page.classList.toggle('active',page.dataset.page===name));
  $$('.nav-item').forEach(item=>item.classList.toggle('active',item.dataset.route===name));
  $('#headerSubtitle').textContent={home:'Актуальные колёса',stats:'Статистика',sources:'Источники',profile:'Профиль'}[name];
  window.scrollTo({top:0,behavior:'smooth'});
}
function updateTimers(){$$('[data-deadline]').forEach(element=>element.textContent=timeLeft(element.dataset.deadline))}
function openUrl(value){
  const url=safeUrl(value);
  if(!url)return;
  try{url.includes('t.me/')?tg?.openTelegramLink?.(url):tg?.openLink?.(url,{try_instant_view:false})}catch{}
  if(!tg)window.open(url,'_blank','noopener');
}

function botUsername(){
  const params=new URLSearchParams(location.search);
  const fromQuery=(params.get('bot')||'').replace(/^@/,'');
  const fromConfig=String(window.BB_CONFIG?.botUsername||'').replace(/^@/,'');
  const value=fromQuery||fromConfig||localStorage.getItem('bbvg:botUsername')||'';
  if(value)try{localStorage.setItem('bbvg:botUsername',value)}catch{}
  return value;
}
function normalizeSource(value){return String(value||'').trim().replace(/^https?:\/\/t\.me\//i,'').replace(/^@/,'').split(/[/?#]/)[0]}
function knownSource(username){const key=username.toLowerCase();return app.data.primary.some(item=>item.toLowerCase()===key)||app.data.nightly.some(item=>item.toLowerCase()===key)}
async function submitSourceRequest(raw){
  const username=normalizeSource(raw);
  if(!/^[A-Za-z][A-Za-z0-9_]{3,31}$/.test(username)){toast('Введите корректный username канала');haptic('warning');return}
  if(knownSource(username)){toast('Этот источник уже проверяется');return}
  const bot=botUsername();
  if(bot){
    const link=`https://t.me/${encodeURIComponent(bot)}?start=source_${encodeURIComponent(username)}`;
    toast('Открываю запрос в боте');
    haptic('success');
    try{tg?.openTelegramLink?.(link)}catch{}
    if(!tg)window.open(link,'_blank','noopener');
    return;
  }
  if(tg?.sendData){
    try{tg.sendData(JSON.stringify({type:'source_request',source:username,version:1}));return}catch(error){console.warn(error)}
  }
  const command=`/source ${username}`;
  try{
    await navigator.clipboard.writeText(command);
    toast('Команда скопирована. Отправьте её боту.');
  }catch{
    showDialog(`<h2>Отправьте запрос боту</h2><p>Скопируйте и отправьте эту команду в чат с ботом:</p><div class="card"><strong>${esc(command)}</strong></div>`);
  }
}

function showSourceInfo(source){
  const primary=app.data.primary.some(item=>item.toLowerCase()===source.toLowerCase());
  const mode=primary?'Основная проверка':'Ночное наблюдение';
  const stats=sourceStats(source);
  const wheels=Number(stats?.wheel_posts||0);
  const activations=Number(stats?.activation_sent||0);
  showDialog(`<h2>@${esc(source)}</h2><p>${esc(mode)}</p><article class="card"><div class="setting"><div class="setting-copy"><strong>Постов с колёсами</strong><small>За всё накопленное время</small></div><span class="row-value">${num(wheels)}</span></div><div class="setting"><div class="setting-copy"><strong>Подтверждённых активаций</strong><small>Успешно подтверждено монитором</small></div><span class="row-value">${num(activations)}</span></div></article><div class="actions"><button class="button primary" data-action="open-url" data-url="https://t.me/${esc(source)}">Открыть Telegram</button><button class="button secondary" data-action="close-dialog">Закрыть</button></div>`);
}
function showDialog(html){const dialog=$('#dialog');$('#dialogBody').innerHTML=html;dialog.showModal?.()}
function closeDialog(){$('#dialog').close?.()}
function renderFatal(){$('#page-home').innerHTML='<div class="empty">Не удалось загрузить данные. Нажмите кнопку обновления.</div>';route('home')}

function bindEvents(){
  document.addEventListener('click',event=>{
    const routeButton=event.target.closest('[data-route]');
    if(routeButton){route(routeButton.dataset.route);haptic('selection');return}
    const actionButton=event.target.closest('[data-action]');
    if(actionButton){
      const action=actionButton.dataset.action;
      if(action==='join')toggleJoined(actionButton.dataset.id);
      else if(action==='open-url'){haptic('light');openUrl(actionButton.dataset.url)}
      else if(action==='source-info'){haptic('selection');showSourceInfo(actionButton.dataset.source)}
      else if(action==='close-dialog'){haptic('selection');closeDialog()}
      else haptic('selection');
      return;
    }
    const day=event.target.closest('[data-days]');
    if(day){app.days=Number(day.dataset.days)||7;renderStats();haptic('selection');return}
    const mode=event.target.closest('[data-source-mode]');
    if(mode){app.sourceMode=mode.dataset.sourceMode;renderSources();haptic('selection');return}
    const setting=event.target.closest('[data-setting]');
    if(setting){
      const key=setting.dataset.setting;
      if(!Object.prototype.hasOwnProperty.call(app.settings,key))return;
      const wasHapticsEnabled=app.settings.haptics;
      if(key==='haptics'&&wasHapticsEnabled)haptic('selection');
      app.settings[key]=!app.settings[key];
      store.set('settings',app.settings);
      if(key==='lightTheme')applyTheme();
      renderProfile();
      if(key==='haptics'&&app.settings.haptics)haptic('success');
      else if(key!=='haptics')haptic('selection');
    }
  });
  document.addEventListener('submit',event=>{
    if(event.target.id==='sourceRequestForm'){
      event.preventDefault();
      submitSourceRequest($('#sourceRequestInput').value);
    }
  });
  document.addEventListener('input',event=>{
    if(event.target.id==='sourceSearch'){
      app.query=event.target.value;
      const card=event.target.nextElementSibling;
      card.innerHTML=filteredSources().slice(0,100).map(sourceRow).join('')||'<div class="empty">Источники не найдены.</div>';
    }
  });
  $('#refreshButton').addEventListener('click',()=>loadData(false));
  $('#dialog').addEventListener('click',event=>{if(event.target===$('#dialog'))closeDialog()});
}

async function init(){
  setupTelegram();
  bindEvents();
  await loadUser();
  await loadData(true);
  route('home');
  setInterval(updateTimers,1000);
  setInterval(()=>{if(app.settings.autoRefresh&&document.visibilityState==='visible')loadData(true)},60000);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&app.settings.autoRefresh)loadData(true)});
  if('serviceWorker'in navigator)navigator.serviceWorker.register('./service-worker.js?v=5.1.0').catch(console.warn);
}
init();
