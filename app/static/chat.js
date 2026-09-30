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
  var j = document.getElementById("job");
  if (j) {
    var url = j.getAttribute("data-url");
    setInterval(function () {
      fetch(url, {credentials: "same-origin"}).then(function (r) { return r.json(); }).then(function (x) {
        if (x.stato !== "in_corso") { location.reload(); }
      }).catch(function () {});
    }, 4000);
  }
})();
