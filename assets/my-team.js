/* "Remember my team" on the hub. Loaded right after the picker and the
   card template, without defer, so it runs while the page is parsed: the
   saved team's card is copied into the slot before anything below it is
   laid out. The team is kept on this device only (localStorage
   hm-tickets-team); nothing is fetched or sent. tickets.js wires the
   picker, Forget and the team pages' button. */
(function () {
  'use strict';
  var slug = '';
  try { slug = localStorage.getItem('hm-tickets-team') || ''; } catch (e) { return; }
  if (!/^[a-z0-9-]{2,40}$/.test(slug)) return;
  var tpl = document.getElementById('my-team-cards');
  var slot = document.querySelector('[data-my-team-slot]');
  if (!tpl || !tpl.content || !slot) return;
  var card = tpl.content.querySelector('[data-team="' + slug + '"]');
  if (!card) return;
  slot.appendChild(card.cloneNode(true));
  var select = document.querySelector('[data-my-team-select]');
  if (select) select.value = slug;
})();
