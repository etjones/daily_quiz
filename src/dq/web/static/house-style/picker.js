/* picker.js — the style picker, built for any page rather than for the
   specimen in particular.

   Two ways of carrying themes, detected at load:
     inline  <style class="hs-theme" data-id data-name data-blurb> blocks,
             switched by flipping `media` between 'all' and 'not all'.
             (`disabled` is not a content attribute on <style>, so every
             theme would apply until JS ran.) This is what a built,
             self-contained artifact uses.
     linked  a single <link id="hs-theme-css" data-href-pattern> whose href
             is rewritten, with metadata from window.THEMES. This is the
             development path, where themes are still separate files.

   The toolbar markup is created here; a host page supplies no HTML. State is
   read and written by ui/boot.js at first paint and kept in sync here. */
(function () {
  var root = document.documentElement;
  var key = root.dataset.pickerKey || 'hs';
  var mq = matchMedia('(prefers-color-scheme: light)');

  /* Two stores, on purpose. localStorage is the client's own memory; the
     cookie exists so a server rendering the page can choose the same theme
     before it sends any HTML — without it, a server-rendered app flashes its
     default theme on every navigation. Static pages simply ignore it. */
  function save(name, value) {
    try { localStorage.setItem(key + ':' + name, value); } catch (e) {}
    try {
      document.cookie = 'hs_' + name + '=' + encodeURIComponent(value) +
        ';path=/;max-age=31536000;samesite=lax';
    } catch (e) {}
  }

  /* ---------- where the themes are ---------- */

  var sheets = [].slice.call(document.querySelectorAll('style.hs-theme'));
  var link = document.getElementById('hs-theme-css');
  var registry = (window.THEMES && window.THEMES.themes) || [];

  var themes = sheets.length
    ? sheets.map(function (s) {
        return { id: s.dataset.id, name: s.dataset.name || s.dataset.id,
                 blurb: s.dataset.blurb || '' };
      })
    : registry.map(function (t) {
        return { id: t.id, name: t.name || t.id, blurb: t.blurb || '' };
      });

  if (!themes.length) return;

  function meta(id) {
    for (var i = 0; i < themes.length; i++) if (themes[i].id === id) return themes[i];
    return null;
  }

  /* ---------- applying ---------- */

  function setTheme(id) {
    if (!meta(id)) return;
    root.dataset.theme = id;
    sheets.forEach(function (s) {
      s.media = (s.dataset.id === id) ? 'all' : 'not all';
    });
    if (link) {
      link.href = (link.dataset.hrefPattern || 'css/themes/{id}.css').replace('{id}', id);
    }
    save('theme', id);
    if (themePick) themePick.value = id;
    if (blurb) blurb.textContent = (meta(id) || {}).blurb || '';
  }

  function setMode(pref) {
    root.dataset.modePref = pref;
    root.dataset.mode = (pref === 'auto') ? (mq.matches ? 'light' : 'dark') : pref;
    save('mode', pref);
    if (modePick) modePick.value = pref;
  }

  /* ---------- chrome ---------- */

  function option(value, label, extra) {
    var o = document.createElement('option');
    o.value = value;
    o.textContent = label;
    if (extra) o.dataset.blurb = extra;
    return o;
  }

  var bar = document.createElement('div');
  bar.className = 'hs-picker';
  bar.setAttribute('role', 'group');
  bar.setAttribute('aria-label', 'Page style');

  var themePick = null;
  if (themes.length > 1) {
    themePick = document.createElement('select');
    themePick.setAttribute('aria-label', 'Theme');
    themes.forEach(function (t) { themePick.appendChild(option(t.id, t.name, t.blurb)); });
    themePick.addEventListener('change', function () { setTheme(themePick.value); });
    bar.appendChild(themePick);
  }

  var modePick = document.createElement('select');
  modePick.setAttribute('aria-label', 'Colour mode');
  [['dark', 'Dark'], ['light', 'Light'], ['auto', 'Auto']].forEach(function (m) {
    modePick.appendChild(option(m[0], m[1]));
  });
  modePick.addEventListener('change', function () { setMode(modePick.value); });
  bar.appendChild(modePick);

  var blurb = document.createElement('span');
  blurb.className = 'hs-blurb';
  bar.appendChild(blurb);

  var close = document.createElement('button');
  close.className = 'hs-close';
  close.type = 'button';
  close.textContent = '×';
  close.title = 'Hide this picker (reload to bring it back)';
  close.setAttribute('aria-label', 'Hide the style picker');
  /* Not persisted: a control you can permanently lose is worse than one you
     dismiss per visit. */
  close.addEventListener('click', function () { bar.remove(); });
  bar.appendChild(close);

  document.body.appendChild(bar);

  /* ---------- initial state (boot.js already chose it) ---------- */

  setTheme(meta(root.dataset.theme) ? root.dataset.theme : themes[0].id);
  setMode(root.dataset.modePref || 'dark');

  mq.addEventListener('change', function () {
    if (root.dataset.modePref === 'auto') setMode('auto');
  });

  window.HouseStyle = {
    themes: themes,
    setTheme: setTheme,
    setMode: setMode,
    hide: function () { bar.remove(); }
  };
})();
