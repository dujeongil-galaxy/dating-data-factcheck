/* ==========================================================================
   首页「新站公告」弹窗 —— 5 秒锁定，只能点 × 关闭
   --------------------------------------------------------------------------
   站长 2026-11-13 指令：照 shuangxiugou 首页弹窗的逻辑，在第三个新站也做一个；
   这次锁定 5 秒，**只能按右上角 × 关闭，点空白区域（遮罩）不会关**。
   内容里备注「这是站长的第三个新网站」，并用链接指向该站——
   站长 2026-11-13 更正：第三个新网站就是
   https://dujeongil-galaxy.github.io/a-reason-for-korea/ （哈韩，也要有一个理由）。

   与 shuangxiugou 版一致的三条约束：
     ① 遮罩不绑定任何关闭事件；② 不监听 Esc；③ × 是唯一关闭入口。
   锁定期内点 × 也无效（抖动提示），到点后文案改为「点右上角 × 关闭」。
   键盘用户可 Tab 到 ×（原生 <button>）按 Enter 关闭，可访问性不丢。

   零依赖：样式与 DOM 全部由本文件注入，不改页面原有 CSS / 结构。
   ========================================================================== */
(function () {
  'use strict';

  var CONFIG = {
    lockMs: 5000,                 // 锁定 5 秒，期间 × 也点不动
    autoDelayMs: 800,             // 首屏加载后延迟弹出（每次刷新首页都弹，不设冷却）
    title: '一个数字，先别急着信',
    lead:
      '网上流传的「25–35 岁男性无房无车相亲成功率 12%、有房后 45%」，' +
      '我们全网检索没找到原始报告，于是把能查到的公开报道与调查一并摊开。' +
      '这里不劝退谁，也不替谁下结论；只把「可查证的」和「查无出处的」分开写清楚。',
    points: [
      '找不到出处的数字，就标明找不到',
      '可查证的部分，附来源、日期与样本口径',
      '比起结论，更想留住「先问一句」的习惯'
    ],
    // 备注 + 指向第三个新网站的链接（2026-11-13 站长更正：第三个站就是 a-reason-for-korea）
    notePrefix: '备注 · 这是站长的第三个新网站：',
    noteLink: {
      text: '哈韩，也要有一个理由',
      href: 'https://dujeongil-galaxy.github.io/a-reason-for-korea/'
    },
    countLabel: '秒后可关闭',
    readyLabel: '点右上角 × 关闭'
  };

  var LOCK_MS = 5000;             // 检查器按这个常量核对，改时长要同步改断言
  var box = null;
  var unlockAt = 0;
  var timer = null;
  var lastFocus = null;

  function injectStyle() {
    if (document.getElementById('pm-style')) return;
    var css =
      '.pm{position:fixed;inset:0;z-index:1000;display:none;align-items:center;' +
      'justify-content:center;font-family:var(--sans);}' +
      '.pm.is-open{display:flex;}' +
      '.pm__mask{position:absolute;inset:0;background:rgba(28,24,21,.46);' +
      'cursor:default;animation:pm-fade .22s ease;}' +
      '@keyframes pm-fade{from{opacity:0}to{opacity:1}}' +
      '.pm__panel{position:relative;width:min(92vw,440px);max-height:86vh;' +
      'display:flex;flex-direction:column;' +
      'padding:28px 26px 22px;border-radius:16px;' +
      'background:var(--card);color:var(--ink);border:1px solid var(--line);' +
      'box-shadow:0 24px 70px rgba(28,24,21,.28);animation:pm-pop .26s cubic-bezier(.2,.9,.3,1.1);}' +
      '@keyframes pm-pop{from{opacity:0;transform:translateY(12px) scale(.97)}' +
      'to{opacity:1;transform:none}}' +
      '.pm__x{position:absolute;top:10px;right:10px;width:34px;height:34px;' +
      'padding:0;border:0;border-radius:999px;background:rgba(28,24,21,.06);' +
      'color:var(--muted);font-size:21px;line-height:1;cursor:pointer;' +
      'transition:background .15s ease,color .15s ease;}' +
      '.pm__x:hover{background:rgba(28,24,21,.12);color:var(--ink);}' +
      '.pm__x:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}' +
      '.pm__body{flex:1 1 auto;overflow-y:auto;min-height:0;}' +
      '.pm__tag{display:inline-block;margin-bottom:12px;padding:3px 10px;' +
      'border-radius:999px;background:var(--danger-bg);color:var(--danger);' +
      'border:1px solid var(--danger-line);font-size:12px;letter-spacing:.08em;}' +
      '.pm__title{margin:0 0 14px;font-family:var(--serif);font-size:26px;' +
      'line-height:1.35;font-weight:700;}' +
      '.pm__lead{margin:0 0 16px;font-size:14.5px;line-height:1.85;color:var(--muted);}' +
      '.pm__points{margin:0 0 18px;padding-left:18px;font-size:14px;' +
      'line-height:1.9;color:var(--ink);}' +
      '.pm__points li{margin:0 0 4px;}' +
      '.pm__note{margin:0;padding:9px 12px;border-left:3px solid var(--accent);' +
      'background:var(--warn-bg);color:var(--warn);font-size:13px;line-height:1.7;' +
      'flex:0 0 auto;}' +
      '.pm__note-link{color:var(--accent);font-weight:600;text-decoration:underline;' +
      'text-underline-offset:2px;white-space:nowrap;}' +
      '.pm__note-link:hover{color:var(--ink);}' +
      '.pm__note-link:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}' +
      '.pm__count{display:flex;align-items:center;gap:8px;flex-wrap:wrap;' +
      'font-size:12.5px;color:var(--muted);border-top:1px solid var(--line);padding-top:14px;}' +
      '.pm__count__num{font-weight:700;color:var(--accent);font-size:15px;}' +
      '.pm__count__bar{flex:1 1 90px;min-width:60px;height:4px;border-radius:999px;' +
      'background:var(--line);overflow:hidden;}' +
      '.pm__count__bar > i{display:block;height:100%;width:100%;' +
      'background:var(--accent);transition:width .1s linear;}' +
      '.pm__count--ready .pm__count__num{color:var(--ok);}' +
      '.pm__count--ready .pm__count__label{color:var(--ok);font-weight:600;}' +
      '.pm__count--shake{animation:pm-shake .32s ease;}' +
      '@keyframes pm-shake{0%,100%{transform:translateX(0)}' +
      '25%{transform:translateX(-5px)}75%{transform:translateX(5px)}}' +
      '@media (max-width:480px){' +
      '.pm__panel{padding:24px 20px 18px;}.pm__title{font-size:22px;}' +
      '.pm__lead,.pm__points{font-size:13.5px;}}' +
      '@media (prefers-reduced-motion:reduce){' +
      '.pm__mask,.pm__panel,.pm__count--shake{animation:none;}' +
      '.pm__count__bar > i{transition:none;}}';
    var st = document.createElement('style');
    st.id = 'pm-style';
    st.textContent = css;
    document.head.appendChild(st);
  }

  function build() {
    injectStyle();
    box = document.createElement('div');
    box.className = 'pm';
    box.id = 'pm-modal';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-labelledby', 'pm-title');
    box.setAttribute('aria-describedby', 'pm-lead');
    box.innerHTML =
      '<div class="pm__mask"></div>' +
      '<div class="pm__panel">' +
        '<button class="pm__x" type="button" aria-label="关闭弹窗" aria-disabled="true">&times;</button>' +
        '<div class="pm__body">' +
          '<div class="pm__tag">新站公告</div>' +
          '<h2 class="pm__title" id="pm-title"></h2>' +
          '<p class="pm__lead" id="pm-lead"></p>' +
          '<ul class="pm__points"></ul>' +
        '</div>' +
        '<p class="pm__note"></p>' +
        '<div class="pm__count" aria-live="polite">' +
          '<span class="pm__count__num">5</span>' +
          '<span class="pm__count__label"></span>' +
          '<span class="pm__count__bar"><i></i></span>' +
        '</div>' +
      '</div>';

    box.querySelector('.pm__title').textContent = CONFIG.title;
    box.querySelector('.pm__lead').textContent = CONFIG.lead;
    var noteEl = box.querySelector('.pm__note');
    noteEl.textContent = CONFIG.notePrefix;
    var noteLink = document.createElement('a');
    noteLink.className = 'pm__note-link';
    noteLink.href = CONFIG.noteLink.href;
    noteLink.target = '_blank';
    noteLink.rel = 'noopener noreferrer';
    noteLink.textContent = CONFIG.noteLink.text;
    noteEl.appendChild(noteLink);
    box.querySelector('.pm__count__label').textContent = CONFIG.countLabel;
    box.querySelector('.pm__points').innerHTML = CONFIG.points
      .map(function (t) { return '<li>' + t + '</li>'; })
      .join('');

    // 唯一关闭入口：右上角 ×。遮罩不绑定 click，也不监听 Escape。
    var xEl = box.querySelector('.pm__x');
    xEl.onclick = close;

    document.body.appendChild(box);
  }

  function shake() {
    var c = box && box.querySelector('.pm__count');
    if (!c) return;
    c.classList.remove('pm__count--shake');
    void c.offsetWidth;
    c.classList.add('pm__count--shake');
  }

  function close() {
    if (Date.now() < unlockAt) {   // 5 秒未到：点 × 也不关，给个轻提示
      shake();
      return;
    }
    if (box) {
      box.classList.remove('is-open');
      box.setAttribute('aria-hidden', 'true');
    }
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function startCountdown() {
    unlockAt = Date.now() + LOCK_MS;
    var numEl = box.querySelector('.pm__count__num');
    var labelEl = box.querySelector('.pm__count__label');
    var barEl = box.querySelector('.pm__count__bar > i');
    var countEl = box.querySelector('.pm__count');
    var xEl = box.querySelector('.pm__x');
    if (timer) clearInterval(timer);
    function tick() {
      var left = unlockAt - Date.now();
      if (left <= 0) {
        clearInterval(timer);
        timer = null;
        numEl.textContent = '0';
        labelEl.textContent = CONFIG.readyLabel;
        barEl.style.width = '0%';
        countEl.classList.add('pm__count--ready');
        xEl.removeAttribute('aria-disabled');
        return;
      }
      numEl.textContent = String(Math.ceil(left / 1000));
      barEl.style.width = (left / LOCK_MS * 100) + '%';
    }
    tick();
    timer = setInterval(tick, 100);
  }

  function open() {
    if (!box) build();
    lastFocus = document.activeElement;
    box.removeAttribute('aria-hidden');
    box.classList.add('is-open');
    startCountdown();
    var xEl = box.querySelector('.pm__x');
    if (xEl && xEl.focus) xEl.focus();
  }

  function init() {
    // 每次刷新首页都自动弹（无冷却）：延迟 autoDelayMs 后弹出
    setTimeout(function () {
      open();
    }, CONFIG.autoDelayMs);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
