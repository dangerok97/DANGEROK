(function () {
  var c = document.getElementById("chat");
  if (c && c.lastElementChild) { c.lastElementChild.scrollIntoView({block: "end"}); }
  var f = document.getElementById("invio");
  if (f) {
    f.addEventListener("submit", function () {
      var b = document.getElementById("invia"), a = document.getElementById("attesa");
      if (b) { b.disabled = true; }
      if (a) { a.hidden = false; }
    });
  }
})();
