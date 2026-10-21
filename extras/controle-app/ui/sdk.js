// O mural é a mesma tela do plugin do painel web; aqui ele recebe um SDK mínimo que fala com o app.
(function () {
  "use strict";
  const R = window.React;
  window.__HERMES_PLUGIN_SDK__ = {
    React: R,
    hooks: { useState: R.useState, useEffect: R.useEffect, useCallback: R.useCallback, useMemo: R.useMemo, useRef: R.useRef, useContext: R.useContext, createContext: R.createContext },
    fetchJSON: async (url, init) => {
      const metodo = (init && init.method) || "GET";
      const corpo = init && init.body ? JSON.parse(init.body) : undefined;
      const r = await window.controle.mural(url, metodo, corpo);
      if (!r.ok) throw new Error(r.mensagem);
      return r.dados;
    },
  };
  window.__HERMES_PLUGINS__ = {
    register: (nome, componente) => {
      window.__PLUGINS_DO_APP__ = { ...(window.__PLUGINS_DO_APP__ || {}), [nome]: componente };
    },
  };
})();
