/* boot.js — runs in <head>, before first paint, so a stored or shared
   preference never shows up as a flash of the wrong theme.

   Must sit *after* the theme <style> blocks (or the theme <link>) it touches.
   Deliberately duplicates a few lines of picker.js: picker.js loads at the end
   of the body, which is far too late to decide what the first paint looks like. */
(function () {
  var root = document.documentElement;
  var key = root.dataset.pickerKey || 'hs';

  function stored(name) {
    try {
      var v = localStorage.getItem(key + ':' + name);
      if (v) { return v; }
    } catch (e) {}
    /* Server-rendered pages set these; see picker.js. */
    var hit = (' ' + document.cookie).match('[; ]hs_' + name + '=([^;]*)');
    return hit ? decodeURIComponent(hit[1]) : null;
  }

  var params;
  try { params = new URLSearchParams(location.search); } catch (e) { params = null; }
  function asked(name) { return (params && params.get(name)) || stored(name); }

  var pref = asked('mode') || root.dataset.modePref || 'dark';
  root.dataset.modePref = pref;
  root.dataset.mode = (pref === 'auto')
    ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark')
    : pref;

  var sheets = document.querySelectorAll('style.hs-theme');
  var link = document.getElementById('hs-theme-css');
  var ids = [];
  for (var i = 0; i < sheets.length; i++) ids.push(sheets[i].dataset.id);

  var theme = asked('theme');
  if (!theme || (ids.length && ids.indexOf(theme) < 0)) {
    theme = root.dataset.theme || ids[0] || null;
  }
  if (!theme) return;
  root.dataset.theme = theme;

  for (var j = 0; j < sheets.length; j++) {
    sheets[j].media = (sheets[j].dataset.id === theme) ? 'all' : 'not all';
  }
  if (link) {
    link.href = (link.dataset.hrefPattern || 'css/themes/{id}.css').replace('{id}', theme);
  }
})();
