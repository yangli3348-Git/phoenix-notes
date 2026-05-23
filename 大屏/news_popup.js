// 新闻弹窗模块 — 从 popup_data.json 加载，自动弹出+语音播报
var popupEnabled = true;
var popupWait = null;
var popupCloseTimer = null;
var closeScheduled = false;
var popupCtx = null;
var popupSource = null;
var cachedBuffer = null;
var newsQueue = [];
var newsIndex = 0;
var firstRun = true;

// ── 开关控制 ──
function togglePopup() {
  popupEnabled = !popupEnabled;
  var label = document.getElementById('popupSwitchLabel');
  var dot = document.querySelector('#popupSwitch .dot');
  if (popupEnabled) {
    label.textContent = '弹窗播报';
    dot.style.background = '#4a8';
    refreshNewsQueue();
  } else {
    label.textContent = '弹窗关闭';
    dot.style.background = '#844';
    if (popupWait) { clearTimeout(popupWait); popupWait = null; }
    hidePopup();
  }
}

// ── 预加载图片 ──
var preloadedImages = {};
function preloadImage(url, cb) {
  if (!url) { if (cb) cb(false); return; }
  if (preloadedImages[url] === true) { if (cb) cb(true); return; }
  if (preloadedImages[url] === 'loading') return;
  preloadedImages[url] = 'loading';
  var img = new Image();
  img.onload = function() { preloadedImages[url] = true; if (cb) cb(true); };
  img.onerror = function() { preloadedImages[url] = false; if (cb) cb(false); };
  img.src = url;
}

// ── 显示弹窗 ──
function showPopup() {
  if (!newsQueue || !newsQueue.length) { popupWait = setTimeout(showPopup, 30000); return; }
  if (popupWait) { clearTimeout(popupWait); popupWait = null; }
  closeScheduled = false;

  var news = newsQueue[newsIndex % newsQueue.length];
  if (!news) return;

  // 预加载该新闻图片
  var matched = window.popupData ? window.popupData.filter(function(item) {
    return (item.source||'').replace('-world','').toLowerCase() === (news.source||'').toLowerCase() && item.title === news.title;
  }) : [];
  var imgUrl = matched.length && matched[0].images && matched[0].images.length > 0 ? matched[0].images[0] : null;

  // 更新标题（立即显示）
  document.getElementById('popTitle').textContent = news.title || '';
  document.getElementById('popSrcLabel').textContent = news.source.toUpperCase();

  // 显示弹窗
  var p = document.getElementById('newsPopup');
  p.style.display = 'flex';
  p.classList.remove('fadeOut');

  // 预加载图片，失败就回退文字
  if (imgUrl) {
    preloadImage(imgUrl, function(ok) {
      if (ok) {
        document.getElementById('popImage').src = imgUrl;
        document.getElementById('popImage').style.display = 'block';
        document.getElementById('popScript').style.display = 'none';
      } else {
        document.getElementById('popImage').style.display = 'none';
        document.getElementById('popScript').textContent = matched.length ? matched[0].script || '' : '';
        document.getElementById('popScript').style.display = 'flex';
      }
    });
    // 已预加载过就直接显示
    if (preloadedImages[imgUrl] === true) {
      document.getElementById('popImage').src = imgUrl;
      document.getElementById('popImage').style.display = 'block';
      document.getElementById('popScript').style.display = 'none';
    }
  } else {
    document.getElementById('popImage').style.display = 'none';
    document.getElementById('popScript').textContent = matched.length ? matched[0].script || '' : '';
    document.getElementById('popScript').style.display = 'flex';
  }

  playPopupAudio(news);
}

function playPopupAudio(news) {
  if (!news || !popupCtx) popupCtx = new (window.AudioContext || window.webkitAudioContext)();

  function doPlay(buffer) {
    if (popupSource) { try { popupSource.stop(); } catch(e){} }
    popupSource = popupCtx.createBufferSource();
    popupSource.buffer = buffer;
    popupSource.connect(popupCtx.destination);
    popupSource.start(0);
    popupSource.onended = function() {
      if (!closeScheduled) { closeScheduled = true; hidePopup(); }
    };
  }

  if (cachedBuffer) { popupCtx.resume().then(function(){ doPlay(cachedBuffer); }); return; }

  popupCtx.resume().then(function() {
    return fetch(news.audio);
  }).then(function(r) { return r.arrayBuffer(); })
  .then(function(buf) { return popupCtx.decodeAudioData(buf); })
  .then(function(audioBuffer) {
    cachedBuffer = audioBuffer;
    doPlay(audioBuffer);
  }).catch(function(e) { console.log('audio error'); });
}

function hidePopup() {
  if (popupSource) { try { popupSource.stop(); } catch(e){} }
  var p = document.getElementById('newsPopup');
  p.classList.add('fadeOut');
  setTimeout(function(){ p.style.display = 'none'; }, 300);
  cachedBuffer = null;
  popupCtx = null;
  newsIndex++;
  // 如果还有下一条，5秒后弹
  if (newsIndex < newsQueue.length) {
    popupWait = setTimeout(showPopup, 5000);
  }
}

// ── 数据刷新 ──
function refreshNewsQueue() {
  fetch('popup_data.json?_=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data || !data.length) return;
      window.popupData = data;
      var items = data.slice(-5).map(function(item) {
        var src = item.source.replace('-world','').toLowerCase();
        return { page: '', audio: item.audio, title: item.title, source: src, script: item.script };
      });
      if (items.length && JSON.stringify(items) !== JSON.stringify(newsQueue)) {
        var wasEmpty = !newsQueue.length;
        newsQueue = items;
        newsIndex = 0;
        if (popupEnabled) {
          if (popupWait) clearTimeout(popupWait);
          popupWait = setTimeout(showPopup, wasEmpty ? 2000 : 5000);
        }
      }
    }).catch(function(){});
}

// ── 引导页 ──
function showFirstGuide() {
  var p = document.getElementById('newsPopup');
  p.style.display = 'flex';
  p.classList.remove('fadeOut');
  document.getElementById('guidePage').style.display = 'flex';
  document.getElementById('newsPage').style.display = 'none';
}

function unlockAndStart() {
  if (popupCtx) popupCtx.resume().catch(function(){});
  firstRun = false;
  document.getElementById('guidePage').style.display = 'none';
  var p = document.getElementById('newsPopup');
  p.classList.add('fadeOut');
  setTimeout(function(){ p.style.display = 'none'; }, 300);
}

// ── 重写 showPopup 加入引导判断 ──
var _origShowPopup = showPopup;
showPopup = function() {
  if (firstRun && !newsQueue.length) { showFirstGuide(); return; }
  firstRun = false;
  document.getElementById('guidePage').style.display = 'none';
  document.getElementById('newsPage').style.display = 'block';
  _origShowPopup();
};

// ── 初始化 ──
refreshNewsQueue();
setInterval(refreshNewsQueue, 300000);

// 蒙版关闭
document.addEventListener('DOMContentLoaded', function() {
  document.getElementById('newsPopup').addEventListener('click', function(e) {
    if (e.target === this) hidePopup();
  });
});
