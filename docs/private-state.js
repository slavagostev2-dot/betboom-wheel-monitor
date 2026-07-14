'use strict';

(()=>{
  const apiUrl=String(window.BB_CONFIG?.privateStateApiUrl||'').replace(/\/$/,'');
  const initData=String(tg?.initData||'');
  const listeners=new Set();
  const privateState={
    ready:false,
    hiddenWheels:new Set(),
    onState(listener){if(typeof listener==='function'){listeners.add(listener);if(this.ready)listener(this)}},
    async request(path,{method='GET',body}={}){
      if(!apiUrl||!initData)throw new Error('Приватное хранилище пока недоступно');
      const response=await fetch(`${apiUrl}${path}`,{
        method,
        cache:'no-store',
        headers:{
          'Accept':'application/json',
          'Content-Type':'application/json',
          'X-Telegram-Init-Data':initData
        },
        body:body===undefined?undefined:JSON.stringify(body)
      });
      const payload=await response.json().catch(()=>({}));
      if(!response.ok||payload?.ok===false)throw new Error(String(payload?.error||`HTTP ${response.status}`));
      return payload;
    },
    emit(){listeners.forEach(listener=>{try{listener(this)}catch(error){console.warn(error)}})},
    async hideWheel(key,hidden=true){
      const normalized=String(key||'').toLowerCase();
      if(!normalized)return;
      if(hidden)this.hiddenWheels.add(normalized);else this.hiddenWheels.delete(normalized);
      this.emit();
      try{
        await this.request('/v1/me/hidden',{method:'PUT',body:{wheel_key:normalized,hidden}});
      }catch(error){
        if(hidden)this.hiddenWheels.delete(normalized);else this.hiddenWheels.add(normalized);
        this.emit();
        toast('Не удалось сохранить скрытие');
        haptic('error');
        console.warn(error);
      }
    },
    async saveSettings(settings){
      try{await this.request('/v1/me/settings',{method:'PUT',body:{settings}})}catch(error){console.warn('Private settings:',error)}
    }
  };
  window.BBPrivateState=privateState;

  const baseToggleJoined=toggleJoined;
  toggleJoined=async function(id){
    const key=String(id||'').toLowerCase();
    if(!key)return;
    const joined=!app.joined.has(key);
    await baseToggleJoined(key);
    if(!apiUrl||!initData)return;
    try{
      await privateState.request('/v1/me/participation',{method:'PUT',body:{wheel_key:key,joined}});
    }catch(error){
      await baseToggleJoined(key);
      toast('Не удалось сохранить отметку');
      haptic('error');
      console.warn(error);
    }
  };

  submitSourceRequest=async function(raw){
    const username=normalizeSource(raw);
    if(!/^[A-Za-z][A-Za-z0-9_]{3,31}$/.test(username)){toast('Введите корректный username канала');haptic('warning');return}
    if(knownSource(username)){toast('Этот источник уже проверяется');return}
    if(!apiUrl||!initData){toast('Откройте приложение внутри Telegram');haptic('warning');return}
    const button=document.querySelector('#sourceRequestForm .form-button');
    if(button){button.disabled=true;button.textContent='Проверяю…'}
    try{
      const result=await privateState.request('/v1/source-requests',{method:'POST',body:{source:username}});
      const input=document.querySelector('#sourceRequestInput');
      if(input)input.value='';
      toast(result.duplicate?'Заявка уже ожидает решения':'Заявка принята');
      haptic('success');
    }catch(error){
      toast(error.message||'Не удалось отправить заявку');
      haptic('error');
    }finally{
      if(button){button.disabled=false;button.textContent='Отправить'}
    }
  };

  const baseStoreSet=store.set.bind(store);
  store.set=function(key,value){
    baseStoreSet(key,value);
    if(key==='settings'&&privateState.ready)privateState.saveSettings(value);
  };

  function normalizedSettings(value){
    if(!value||typeof value!=='object')return{};
    return Object.fromEntries(Object.entries(value).map(([key,item])=>{
      if(item==='true')return[key,true];
      if(item==='false')return[key,false];
      const numeric=typeof item==='string'&&item.trim()!==''?Number(item):NaN;
      return[key,Number.isFinite(numeric)?numeric:item];
    }));
  }

  async function waitForInitialLoad(){
    for(let attempt=0;attempt<100;attempt+=1){
      const shell=document.querySelector('#app');
      if(app.lastSync||shell?.hidden===false)return;
      await new Promise(resolve=>setTimeout(resolve,100));
    }
  }

  async function hydrate(){
    if(!apiUrl||!initData)return;
    try{
      const session=privateState.request('/v1/session',{method:'POST'});
      await waitForInitialLoad();
      const payload=await session;
      const state=payload?.state||{};
      app.joined=new Set(Array.isArray(state.joined)?state.joined.map(value=>String(value).toLowerCase()):[]);
      app.participationHistory=new Set(Array.isArray(state.participationHistory)?state.participationHistory.map(value=>String(value).toLowerCase()):[]);
      app.joined.forEach(value=>app.participationHistory.add(value));
      privateState.hiddenWheels=new Set(Array.isArray(state.hiddenWheels)?state.hiddenWheels.map(value=>String(value).toLowerCase()):[]);
      if(state.settings&&typeof state.settings==='object'){
        app.settings={...app.settings,...normalizedSettings(state.settings)};
        baseStoreSet('settings',app.settings);
        applyTheme();
      }
      privateState.ready=true;
      privateState.emit();
      renderAll();
    }catch(error){
      console.warn('Private state session:',error);
      toast('Личные данные временно не синхронизированы');
    }
  }

  hydrate();
})();
