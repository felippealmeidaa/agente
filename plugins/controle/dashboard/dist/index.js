// O painel web não tem tela própria do controle: a interface fica no Hermes Desktop (desktop/plugin.js).
(function () {
  "use strict";
  if (window.__HERMES_PLUGINS__) window.__HERMES_PLUGINS__.register("controle", function () { return null; });
})();
