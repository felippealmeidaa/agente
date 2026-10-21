// Ponte mínima entre a tela e o processo principal: só estas chamadas existem.
const { contextBridge, ipcRenderer } = require("electron");

const chamar = (nome) => (...args) => ipcRenderer.invoke(nome, ...args);

contextBridge.exposeInMainWorld("controle", {
  estado: chamar("estado"),
  salvarPolitica: chamar("politica:salvar"),
  pausar: chamar("pausar"),
  pararTudo: chamar("parar-tudo"),
  responder: chamar("pedido:responder"),
  atividade: chamar("atividade"),
  integridade: chamar("integridade"),
  processos: chamar("processos"),
  encerrar: chamar("processo:encerrar"),
  escolherPasta: chamar("pasta:escolher"),
  abrirPasta: chamar("pasta:abrir"),
  mural: chamar("mural"),
  aoMudar: (nome, funcao) => {
    if (!["pedidos", "politica"].includes(nome)) return () => {};
    const ouvinte = (_e, dados) => funcao(dados);
    ipcRenderer.on(nome, ouvinte);
    return () => ipcRenderer.removeListener(nome, ouvinte);
  },
});
