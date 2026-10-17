/* Road trip planner. Everything runs in the browser from the data embedded
   in the page (#rt-data): games with their SeatGeek get-in price, team
   cities and the arena-to-arena distance table. Nothing is fetched.

   A trip is 2 to 4 games, one a day, each at most 2 days after the one
   before, all inside the chosen number of days, starting between the two
   dates. Each hop is at most maxHop miles (straight line); under `drivable`
   it is marked drivable, otherwise a short flight. Trips are ranked by the
   total get-in price for one ticket per game. */
(function () {
  'use strict';
  var el = document.getElementById('rt-data');
  var form = document.getElementById('rt-form');
  if (!el || !form) return;
  var D = JSON.parse(el.textContent);
  var status = document.getElementById('rt-status');
  var out = document.getElementById('rt-results');
  var DAY = 86400000;
  var MAX_GAP = 2, KEEP = 25;

  // [date, time, home, away, price, median, listings, sgUrl, tmUrl, matchupSlug]
  var games = D.games.map(function (g, i) {
    return { i: i, date: g[0], day: Math.round(Date.parse(g[0] + 'T00:00:00Z') / DAY), time: g[1],
      home: g[2], away: g[3], price: g[4], median: g[5], listings: g[6], sg: g[7], tm: g[8], slug: g[9] };
  });
  var byDay = {};
  games.forEach(function (g) { (byDay[g.day] = byDay[g.day] || []).push(g); });

  function miles(a, b) { return (D.miles[a] && D.miles[a][b] != null) ? D.miles[a][b] : Infinity; }
  function dayOf(s) { return Math.round(Date.parse(s + 'T00:00:00Z') / DAY); }
  function fmtDay(day) {
    var d = new Date(day * DAY);
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
  }
  function money(v) { return '$' + Math.round(v).toLocaleString('en-US'); }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return '&#' + c.charCodeAt(0) + ';'; }); }
  function time12(t) {
    if (!t) return 'Time TBD';
    var h = +t.slice(0, 2), m = t.slice(3, 5);
    return ((h % 12) || 12) + ':' + m + (h < 12 ? ' AM' : ' PM');
  }

  // Default dates: from the first game, two weeks of start dates.
  var first = D.first, today = new Date().toISOString().slice(0, 10);
  if (today > first && today <= D.last) first = today;
  form.from.value = first;
  form.to.value = new Date((dayOf(first) + 13) * DAY).toISOString().slice(0, 10);

  function search(opt) {
    var results = [];
    var worst = Infinity;
    function consider(trip, total) {
      if (results.length >= KEEP && total >= worst) return;
      results.push({ games: trip.slice(), total: total });
      if (results.length > KEEP * 4) trim();
    }
    function trim() {
      results.sort(function (a, b) { return a.total - b.total || a.games[0].day - b.games[0].day; });
      results.length = Math.min(results.length, KEEP);
      worst = results.length >= KEEP ? results[results.length - 1].total : Infinity;
    }
    function hasTeam(trip) {
      if (!opt.team) return true;
      for (var k = 0; k < trip.length; k++) if (trip[k].home === opt.team || trip[k].away === opt.team) return true;
      return false;
    }
    function extend(trip, total) {
      var n = trip.length;
      if (n >= opt.min && hasTeam(trip)) consider(trip, total);
      if (n >= opt.max) return;
      var last = trip[n - 1];
      var endDay = trip[0].day + opt.days - 1;
      for (var d = last.day + 1; d <= Math.min(last.day + MAX_GAP, endDay); d++) {
        var list = byDay[d] || [];
        for (var j = 0; j < list.length; j++) {
          var g = list[j];
          var t = total + g.price;
          if (t > opt.budget) continue;
          if (results.length >= KEEP && t >= worst) continue;
          if (miles(last.home, g.home) > opt.maxHop) continue;
          trip.push(g);
          extend(trip, t);
          trip.pop();
        }
      }
    }
    for (var s = opt.from; s <= opt.to; s++) {
      (byDay[s] || []).forEach(function (g) { if (g.price <= opt.budget) extend([g], g.price); });
    }
    trim();
    return results;
  }

  function render(results, opt) {
    if (!results.length) {
      status.textContent = 'No trips match. Try more days, a bigger budget or a wider date range.';
      out.innerHTML = '';
      return;
    }
    status.textContent = 'Cheapest ' + results.length + ' trip' + (results.length > 1 ? 's' : '') + ', one get-in ticket per game.';
    out.innerHTML = results.map(function (r, idx) {
      var g0 = r.games[0], gN = r.games[r.games.length - 1];
      var span = gN.day - g0.day + 1;
      var rows = r.games.map(function (g, k) {
        var home = D.teams[g.home], away = D.teams[g.away];
        var hop = '';
        if (k > 0) {
          var mi = miles(r.games[k - 1].home, g.home);
          hop = mi === 0 ? 'same arena' : (mi + ' mi, ' + (mi <= D.drivable ? 'drivable' : 'short flight'));
          hop = '<span class="hop">from ' + esc(D.teams[r.games[k - 1].home][1]) + ': ' + hop + '</span>';
        }
        return '<li><span>' + hop + '<span class="hop">' + esc(fmtDay(g.day)) + ' · ' + time12(g.time) + ' · ' + esc(home[1]) + '</span>' +
          '<a href="' + esc(D.base + g.slug + '/') + '">' + esc(away[0]) + ' at ' + esc(home[0]) + '</a></span>' +
          '<span><a class="price" href="' + esc(g.sg) + '" target="_blank" rel="' + (D.sponsored ? 'sponsored nofollow noopener' : 'nofollow noopener') + '">' + money(g.price) + '</a></span></li>';
      }).join('');
      return '<article class="trip"><div class="trip-head"><h3>' + (idx + 1) + '. ' + r.games.length + ' games in ' + span + ' days, ' +
        esc(fmtDay(g0.day)) + (span > 1 ? ' to ' + esc(fmtDay(gN.day)) : '') + '</h3>' +
        '<span class="trip-total">' + money(r.total) + '</span></div><ol>' + rows + '</ol></article>';
    }).join('');
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var n = +form.games.value;
    var opt = {
      days: +form.days.value,
      min: n || 2, max: n || 4,
      from: dayOf(form.from.value), to: dayOf(form.to.value),
      budget: form.budget.value === '' ? Infinity : +form.budget.value,
      team: form.team.value,
      maxHop: form.hops.value === 'drive' ? D.drivable : D.maxHop
    };
    if (isNaN(opt.from) || isNaN(opt.to) || opt.to < opt.from) {
      status.textContent = 'Pick an earliest start on or before the latest start.';
      return;
    }
    if (opt.min > opt.days) {
      status.textContent = opt.min + ' games need at least ' + opt.min + ' days.';
      out.innerHTML = '';
      return;
    }
    render(search(opt), opt);
  });
})();
