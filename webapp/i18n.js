/* Английская версия интерфейса игрока.
   Тексты в разметке и коде написаны по-русски; этот модуль переводит каждый текст при появлении на экране
   (словарь точных фраз + шаблоны для фраз с числами). Админка (#admin-root) не переводится. */
(function () {
  const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
  let saved = null; try { saved = localStorage.getItem('lang'); } catch {}
  const code = (tgUser?.language_code || navigator.language || 'ru').slice(0, 2).toLowerCase();
  const RU_LIKE = ['ru', 'uk', 'be', 'kk', 'uz', 'ky', 'tg', 'hy', 'az', 'ka'];
  const LANG = saved || (RU_LIKE.includes(code) ? 'ru' : 'en');
  window.LANG = LANG;
  window.setLang = l => { try { localStorage.setItem('lang', l); } catch {} location.reload(); };
  document.documentElement.lang = LANG;
  if (LANG !== 'en') { window.tr = s => s; return; }

  const EN = {
    'Баланс': 'Balance', 'Обучение': 'Tutorial', 'Пополнить': 'Top up', 'Вывести': 'Withdraw', 'Чек': 'Check',
    'Как начать майнить': 'How to start mining', 'Арендуйте сервер': 'Rent a server',
    'В магазине — выберите любой тариф на 30 дней': 'Pick any plan in the shop for 30 days',
    'Сервер майнит сам': 'The server mines on its own', 'Круглосуточно, даже когда приложение закрыто': '24/7, even when the app is closed',
    'Забирайте раз в сутки': 'Claim once a day',
    'Хранилище копит монеты сутки — затем нажмите «Забрать», чтобы майнинг продолжился. Бот напомнит': 'Storage fills up in 24 hours — then tap “Claim” to keep mining. The bot will remind you',
    'Выводите TON': 'Withdraw TON', 'Вывод на ваш TON-кошелёк': 'Withdraw to your TON wallet', 'Выбрать сервер': 'Choose a server',
    'Забрать': 'Claim', 'Мои серверы': 'My servers',
    'Серверы майнят, пока действует аренда. Следите за сроком и продлевайте вовремя.': 'Servers mine while the rental is active. Keep an eye on the term and renew in time.',
    'Комиссия сервиса': 'Service fee', 'Аренда': 'Rentals', 'Арендовать ещё сервер': 'Rent another server',
    'Улучшение переводит сервер на тариф выше и не тратит склад. Срок аренды при улучшении сохраняется.': 'An upgrade moves the server to the next plan and doesn’t use stock. The rental term stays the same.',
    'Друзья': 'Friends', 'Бонус за приглашение': 'Invite bonus', 'когда друг арендует первый сервер': 'when your friend rents their first server',
    'Пригласить': 'Invite', 'Копировать': 'Copy', 'Ваши друзья': 'Your friends', 'Миссии': 'Missions',
    'Награды зачисляются на баланс сразу после выполнения.': 'Rewards are credited to your balance right after completion.',
    'Магазин': 'Shop', 'Арендуйте серверы для майнинга и выбирайте скин вентилятора.': 'Rent mining servers and pick a fan skin.',
    'Серверы': 'Servers', 'Скины вентилятора': 'Fan skins',
    'Любую покупку можно оплатить с баланса, TON-кошельком или Telegram Stars.': 'Pay for anything with your balance, a TON wallet or Telegram Stars.',
    'Аккаунт заблокирован': 'Account blocked',
    'Доступ к майнингу ограничен. Чтобы узнать причину и восстановить аккаунт, обратитесь в техподдержку.': 'Access to mining is restricted. Contact support to find out why and restore your account.',
    'Написать в поддержку': 'Contact support', 'Закрыть': 'Close', 'Вывод на TON': 'Withdraw to TON', 'Сумма': 'Amount',
    'Количество': 'Amount', 'Вывести всё': 'Withdraw all', 'TON-адрес кошелька': 'TON wallet address', 'UQ… или EQ…': 'UQ… or EQ…',
    'Создать заявку': 'Create request', 'История': 'History', 'Пропустить': 'Skip', 'Далее': 'Next', 'Оплата': 'Payment',
    'С баланса': 'From balance', 'TON-кошелёк': 'TON wallet', 'Tonkeeper, Telegram Wallet и др.': 'Tonkeeper, Telegram Wallet, etc.',
    'Оплата внутри Telegram': 'Pay inside Telegram', 'Пополнение': 'Top-up', 'Сумма в TON': 'Amount in TON',
    'С баланса можно арендовать и улучшать серверы и покупать всё в магазине.': 'Use your balance to rent and upgrade servers and buy anything in the shop.',
    'Оплата в TON': 'Pay with TON', 'Адрес': 'Address', 'Комментарий': 'Comment',
    'Оплатите через TON Connect — сумма и комментарий подставятся сами. Или переведите вручную: обязательно укажите комментарий — по нему мы найдём платёж. Нажмите на строку, чтобы скопировать. Покупка активируется автоматически в течение минуты после поступления.':
      'Pay with TON Connect — the amount and comment are filled in for you. Or send manually: be sure to include the comment, it’s how we find your payment. Tap a row to copy. Your purchase activates automatically within a minute of arrival.',
    'Оплатить через кошелёк': 'Pay with wallet', 'Открыть по ссылке': 'Open via link', 'Я оплатил — проверить': 'I’ve paid — check',
    'Майнинг': 'Mining', 'Ошибка сети': 'Network error', 'Нет серверов': 'No servers', 'Майнинг не запущен': 'Mining not started',
    'Серверы закончились — пополнение в 12:00 МСК': 'Sold out — restock at 12:00 Moscow time',
    'Заберите остаток намайненного': 'Claim the rest of your mined coins', 'Арендуйте сервер, чтобы начать': 'Rent a server to start',
    'Хранилище заполнено — нажмите «Забрать», чтобы майнинг продолжился': 'Storage is full — tap “Claim” to keep mining',
    'Нет работающих серверов': 'No servers running', 'Отключена навсегда': 'Disabled forever', 'Отключить комиссию': 'Remove the fee',
    'У вас пока нет серверов': 'You have no servers yet', 'Истёк': 'Expired', '< 1 дня': '< 1 day',
    'Пополните баланс, чтобы отправить чек': 'Top up your balance to send a check',
    'В любом чате напишите @имя_бота и сумму, например 1.5': 'In any chat type @bot_name and an amount, e.g. 1.5',
    'Пополнение временно недоступно': 'Top-ups are temporarily unavailable', 'В обработке': 'Pending', 'Выплачено': 'Paid',
    'Отклонено': 'Declined', 'Вывод временно недоступен': 'Withdrawals are temporarily unavailable', 'Укажите TON-адрес': 'Enter a TON address',
    'Заявка создана': 'Request created', 'Заявок пока нет': 'No requests yet', 'нет в наличии': 'out of stock', 'Нет': 'Sold out',
    'Надет': 'Equipped', 'Надеть': 'Equip', 'Стандарт': 'Default', 'Бесплатно': 'Free', 'Есть': 'Owned', 'Скин применён': 'Skin applied',
    'Оплата не прошла': 'Payment failed', 'Скопировано': 'Copied', 'Не удалось скопировать': 'Couldn’t copy', 'отключить': 'disconnect',
    'Платёж отправлен, ждём подтверждения…': 'Payment sent, waiting for confirmation…', 'Оплата отменена': 'Payment cancelled',
    'TON Connect не загрузился, используйте ссылку': 'TON Connect failed to load, use the link',
    'Платёж пока не найден, попробуйте через минуту': 'Payment not found yet, try again in a minute',
    'Пригласите первого друга': 'Invite your first friend', 'Игрок': 'Player', 'Присоединяйся к TonCry': 'Join TonCry',
    'Ссылка скопирована': 'Link copied', 'Готово': 'Done', 'Получить': 'Claim', 'Награда получена': 'Reward received',
    'Добро пожаловать!': 'Welcome!',
    'Арендуйте облачные серверы — они майнят TON для вас круглосуточно. Разберёмся за минуту.': 'Rent cloud servers — they mine TON for you around the clock. Let’s get you set up in a minute.',
    'Забирайте намайненное': 'Claim your rewards',
    'Пополняйте баланс, оплачивайте им серверы и выводите прибыль на свой TON-кошелёк.': 'Top up your balance, pay for servers with it and withdraw profits to your TON wallet.',
    'Здесь ваши монеты. Пополняйте баланс в TON и выводите на кошелёк.': 'Your coins live here. Top up with TON and withdraw to your wallet.',
    'Вентилятор крутится, пока работают серверы. Кольцо показывает, насколько заполнено хранилище.': 'The fan spins while your servers work. The ring shows how full the storage is.',
    'Переводит намайненное на баланс и освобождает хранилище.': 'Moves mined coins to your balance and empties the storage.',
    'Срок аренды, доход, улучшение и продление каждого сервера.': 'Rental term, income, upgrades and renewals for each server.',
    'Аренда серверов и скины вентилятора. Начните отсюда!': 'Server rentals and fan skins. Start here!',
    'Показать, где что': 'Show me around', 'Понятно': 'Got it', 'Откройте в Telegram': 'Open in Telegram',
    'Ежедневный бонус': 'Daily bonus', 'Пополните баланс': 'Top up your balance', 'Причина': 'Reason',
  };
  const pl = (n, one, many) => `${n} ${+n === 1 ? one : many}`;
  const P = [
    [/^(\d+) сервер(?:а|ов)?$/, (m, n) => pl(n, 'server', 'servers')],
    [/^(\d+) сервер(?:а|ов)? работа(?:ет|ют)$/, (m, n) => pl(n, 'server', 'servers') + ' running'],
    [/^×(\S+) буст$/, '×$1 boost'],
    [/^(.+) GH\/s · комиссия (\d+)%$/, '$1 GH/s · fee $2%'],
    [/^Аренда на (\d+) дней · продлевайте во вкладке «Серверы»$/, 'Rented for $1 days · renew in the “Servers” tab'],
    [/^Арендуйте сервер — первый со скидкой (\d+)%, от (.+) TON$/, 'Rent a server — your first one is $1% off, from $2 TON'],
    [/^Арендуйте сервер от (.+) TON$/, 'Rent a server from $1 TON'],
    [/^≈ (.+) в день · заполнится через (?:(\d+) ч )?(\d+) мин$/, (m, a, h, mm) => `≈ ${a} per day · full in ${h ? h + ' h ' : ''}${mm} min`],
    [/^≈ (.+) TON в день$/, '≈ $1 TON per day'],
    [/^(.+) — готово$/, (m, a) => `${tr(a)} — done`],
    [/^(.+) — активировано$/, (m, a) => `${tr(a)} — activated`],
    [/^На балансе (.+)$/, 'Balance: $1'],
    [/^Не хватает (.+) — пополните баланс$/, '$1 short — top up your balance'],
    [/^(\d+)% с майнинга · отключается навсегда$/, '$1% of mining · can be removed forever'],
    [/^(.+) GH\/s · ≈ (.+) TON\/день$/, '$1 GH/s · ≈ $2 TON/day'],
    [/^(\d+) (?:день|дня|дней)$/, (m, n) => pl(n, 'day', 'days')],
    [/^Улучшение → (.+) · (.+) GH\/s$/, (m, a, b) => `Upgrade → ${tr(a)} · ${b} GH/s`],
    [/^Улучшить · (.+) TON$/, 'Upgrade · $1 TON'],
    [/^Улучшить до (.+)$/, (m, a) => `Upgrade to ${tr(a)}`],
    [/^Продлить · (.+) TON$/, 'Renew · $1 TON'],
    [/^Продлить (.+) на (\d+) дней$/, (m, a, d) => `Renew ${tr(a)} for ${d} days`],
    [/^Минимальная сумма — (.+)\. Заявки обрабатываются вручную, обычно в течение 24 часов\.$/, 'Minimum amount is $1. Requests are processed manually, usually within 24 hours.'],
    [/^от (.+)$/, 'from $1'],
    [/^Минимум (.+)$/, 'Minimum $1'],
    [/^Серверы · первый −(\d+)%$/, 'Servers · first one −$1%'],
    [/^Аренда на (\d+) дней\. Склад пополняется каждый день в 12:00 МСК \(через (\d+) ч\)\.(?: Доход указан с учётом комиссии (\d+)%\.)?$/,
      (m, d, h, f) => `Rented for ${d} days. Stock refills daily at 12:00 Moscow time (in ${h} h).` + (f ? ` Income shown after the ${f}% fee.` : '')],
    [/^осталось (\d+) шт$/, '$1 left'],
    [/^Сервер (.+)$/, (m, a) => `Server ${tr(a)}`],
    [/^Кошелёк (.+) · $/, 'Wallet $1 · '],
    [/^\+(.+) за каждого друга$/, '+$1 per friend'],
    [/^Ваши друзья · (\d+)$/, 'Your friends · $1'],
    [/^(\d+) из (\d+)$/, '$1 of $2'],
    [/^Напишите в любом чате @(.+) и сумму$/, 'Type @$1 and an amount in any chat'],
    [/^Выберите тариф в магазине\. Аренда — на (\d+) дней\. Первый сервер со скидкой (\d+)%\.$/, 'Pick a plan in the shop. Rentals last $1 days. Your first server is $2% off.'],
    [/^Монеты копятся в хранилище .+\. Заходите раз в день и жмите «Забрать», чтобы майнинг продолжился\. Бот пришлёт напоминание\.$/,
      'Coins pile up in storage for 24 hours. Come back daily and tap “Claim” to keep mining. The bot will remind you.'],
  ];
  const SPEC = /(\d+) (?:ядро|ядра|ядер) \/ (\d+) GB RAM/g;
  const CYR = /[А-Яа-яЁё]/;
  function tr(s) {
    if (!s || !CYR.test(s)) return s;
    const lead = s.match(/^\s*/)[0], tail = s.match(/\s*$/)[0], core = s.trim();
    let out = EN[core];
    if (out === undefined) {
      for (const [rx, rep] of P) if (rx.test(core)) { out = core.replace(rx, rep); break; }
    }
    if (out === undefined && core.includes(' · ')) out = core.split(' · ').map(tr).join(' · ');
    if (out === undefined) out = core;
    return lead + out.replace(SPEC, '$1 vCPU / $2 GB RAM') + tail;
  }
  window.tr = tr;
  const skip = n => n.parentElement?.closest('#admin-root, script, style');
  function fixText(n) { if (!skip(n)) { const v = n.nodeValue, t = tr(v); if (t !== v) n.nodeValue = t; } }
  function fixEl(e) {
    if (e.closest?.('#admin-root')) return;
    for (const a of ['placeholder', 'aria-label', 'title']) { const v = e.getAttribute?.(a); if (v && CYR.test(v)) e.setAttribute(a, tr(v)); }
  }
  function walk(root) {
    if (root.nodeType === 3) return fixText(root);
    if (root.nodeType !== 1 || root.matches?.('#admin-root, script, style')) return;
    fixEl(root);
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
      acceptNode: n => n.nodeType === 1 && n.matches('#admin-root, script, style') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
    for (let n = w.nextNode(); n; n = w.nextNode()) n.nodeType === 3 ? fixText(n) : fixEl(n);
  }
  function start() {
    walk(document.body);
    new MutationObserver(ms => {
      for (const m of ms) {
        if (m.type === 'characterData') { if (CYR.test(m.target.nodeValue)) fixText(m.target); }
        else if (m.type === 'attributes') fixEl(m.target);
        else m.addedNodes.forEach(walk);
      }
    }).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['placeholder', 'aria-label', 'title'] });
  }
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', start) : start();
})();
