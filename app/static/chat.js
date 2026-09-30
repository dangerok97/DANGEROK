(function () {
  var c = document.getElementById("chat");
  if (c && c.lastElementChild) { c.lastElementChild.scrollIntoView({block: "end"}); }
  function bolla(chi, testo, classe) {
    var m = document.createElement("div"); m.className = "msg " + classe;
    var a = document.createElement("div"); a.className = "chi"; a.textContent = chi;
    var t = document.createElement("div"); t.className = "testo"; t.textContent = testo;
    m.appendChild(a); m.appendChild(t);
    if (c) { c.appendChild(m); m.scrollIntoView({block: "end"}); }
    return m;
  }
  var vivo = null;
  function inCorso(testo) {
    if (testo) { bolla("Tu", testo, "user"); }
    vivo = bolla("Assistente", "sto scrivendo…", "assistant attesa");
  }
  var f = document.getElementById("invio");
  if (f) {
    f.addEventListener("submit", function () {
      var b = document.getElementById("invia"), a = document.getElementById("attesa");
      var ta = f.querySelector("textarea");
      if (ta && ta.value.trim()) { inCorso(ta.value.trim()); }
      if (b) { b.disabled = true; }
      if (a) { a.hidden = false; }
    });
  }
  var j = document.getElementById("job");
  if (j) {
    var url = j.getAttribute("data-url");
    j.hidden = true;
    inCorso(j.getAttribute("data-msg"));
    setInterval(function () {
      fetch(url, {credentials: "same-origin"}).then(function (r) { return r.json(); }).then(function (x) {
        if (x.stato !== "in_corso") { location.reload(); return; }
        if (!x.parziale && x.fase && vivo) { vivo.querySelector(".testo").textContent = "sto scrivendo… (" + x.fase + ")"; }
        if (x.parziale && vivo) { vivo.querySelector(".testo").textContent = x.parziale; vivo.scrollIntoView({block: "end"}); }
      }).catch(function () {});
    }, 1000);
  }
})();
