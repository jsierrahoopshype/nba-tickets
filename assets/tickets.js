/* Hub picker and the team pages' "make this my team" button. */
(function () {
  'use strict';
  var KEY = 'hm-tickets-team';
  function save(slug) {
    try { if (slug) localStorage.setItem(KEY, slug); else localStorage.removeItem(KEY); } catch (e) { /* private mode */ }
  }
  function show(slug) {
    var tpl = document.getElementById('my-team-cards');
    var slot = document.querySelector('[data-my-team-slot]');
    if (!tpl || !slot) return;
    slot.innerHTML = '';
    var card = slug && tpl.content.querySelector('[data-team="' + slug + '"]');
    if (card) slot.appendChild(card.cloneNode(true));
  }
  var select = document.querySelector('[data-my-team-select]');
  if (select) {
    select.addEventListener('change', function () { save(select.value); show(select.value); });
  }
  var clear = document.querySelector('[data-my-team-clear]');
  if (clear) {
    clear.addEventListener('click', function () { save(''); show(''); if (select) select.value = ''; });
  }
  var current = '';
  try { current = localStorage.getItem(KEY) || ''; } catch (e) { /* ignore */ }
  document.querySelectorAll('[data-set-team]').forEach(function (btn) {
    var slug = btn.getAttribute('data-set-team');
    var label = btn.textContent;
    function sync() {
      var on = current === slug;
      btn.textContent = on ? 'Saved as my team' : label;
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    btn.addEventListener('click', function () {
      current = current === slug ? '' : slug;
      save(current);
      sync();
    });
    sync();
  });
})();
