// Progressive enhancement: re-fetch the board fragment from THIS server (never the API) on the
// page's refresh interval while the tab is visible. Without JavaScript the page still works.
(function () {
  var board = document.getElementById('board');
  if (!board || !window.fetch) { return; }
  var every = Math.max(20, parseInt(board.getAttribute('data-refresh'), 10) || 60) * 1000;
  function refresh() {
    if (document.hidden) { return; }
    fetch('/board' + window.location.search, { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) { if (html !== null) { board.innerHTML = html; } })
      .catch(function () { /* keep what is on screen; the server reports its own errors */ });
  }
  setInterval(refresh, every);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) { refresh(); } });
})();
