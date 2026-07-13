function bindEvents() {
  document.addEventListener('click', event => {
    const routeButton = event.target.closest('[data-route]');
    if (routeButton) {
      event.preventDefault();
      route(routeButton.dataset.route);
      return;
    }

    const filterButton = event.target.closest('[data-filter]');
    if (filterButton) {
      app.filter = filterButton.dataset.filter;
      renderWheels();
      return;
    }

    const periodButton = event.target.closest('[data-days]');
    if (periodButton) {
      app.days = Number(periodButton.dataset.days);
      renderStats();
      return;
    }

    const modeButton = event.target.closest('[data-mode]');
    if (modeButton) {
      app.sourceMode = modeButton.dataset.mode;
      app.query = '';
      app.limit = 80;
      renderSources();
      return;
    }

    const settingButton = event.target.closest('[data-setting]');
    if (settingButton) {
      setting(settingButton.dataset.setting);
      return;
    }

    const button = event.target.closest('[data-action]');
    if (!button) return;
    const action = button.dataset.action;
    if (action === 'join') join(button.dataset.id);
    else if (action === 'favorite') favorite(button.dataset.source);
    else if (action === 'open') openLink(button.dataset.url);
    else if (action === 'telegram') openLink(button.dataset.url, true);
    else if (action === 'share') share(button.dataset.id);
    else if (action === 'wheel-info') wheelInfo(button.dataset.id);
    else if (action === 'source-info') sourceInfo(button.dataset.source);
    else if (action === 'more') {
      app.limit += 80;
      renderSources();
    } else if (action === 'refresh') loadData();
    else if (action === 'write') requestBotMessages();
    else if (action === 'home-screen') addHomeShortcut();
  });

  $('#refreshButton').onclick = () => loadData();
  $('#profileButton').onclick = () => route('profile');
  $('#closeDialog').onclick = () => $('#detailsDialog').close();
  $('#detailsDialog').onclick = event => {
    if (event.target === $('#detailsDialog')) event.target.close();
  };
}

function requestBotMessages() {
  if (!tg || typeof tg.requestWriteAccess !== 'function') {
    toast('Доступно только внутри Telegram');
    return;
  }
  tg.requestWriteAccess(granted => toast(granted ? 'Сообщения разрешены' : 'Разрешение не выдано'));
}

function addHomeShortcut() {
  if (!tg || typeof tg.addToHomeScreen !== 'function') {
    toast('Клиент не поддерживает ярлык');
    return;
  }
  tg.addToHomeScreen();
  toast('Подтвердите добавление');
}

function pullRefresh() {
  let start = 0;
  let distance = 0;
  const indicator = $('#pullIndicator');
  addEventListener('touchstart', event => {
    if (scrollY <= 0) start = event.touches[0].clientY;
  }, { passive: true });
  addEventListener('touchmove', event => {
    if (!start || scrollY > 0) return;
    distance = Math.max(0, event.touches[0].clientY - start);
    if (distance > 28) {
      indicator.classList.add('visible');
      indicator.textContent = distance > 72 ? 'Отпустите для обновления' : 'Потяните для обновления';
    }
  }, { passive: true });
  addEventListener('touchend', () => {
    indicator.classList.remove('visible');
    if (distance > 72) loadData();
    start = 0;
    distance = 0;
  }, { passive: true });
}

function updateTimers() {
  $$('[data-deadline]').forEach(element => {
    const deadlineDate = date(element.dataset.deadline);
    if (deadlineDate) element.textContent = left(deadlineDate);
  });
  updateConnection();
}
