// Ícone da bandeja desenhado em tempo de execução: a cor mostra o estado do agente.
const zlib = require("zlib");

const CORES = {
  livre: [74, 222, 128],
  pausado: [255, 189, 56],
  pedido: [251, 44, 54],
};

const TABELA = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(buf) {
  let c = 0xffffffff;
  for (const b of buf) c = TABELA[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function bloco(tipo, dados) {
  const tam = Buffer.alloc(4);
  tam.writeUInt32BE(dados.length);
  const corpo = Buffer.concat([Buffer.from(tipo, "ascii"), dados]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(corpo));
  return Buffer.concat([tam, corpo, crc]);
}

// Anel creme com um ponto colorido no centro
function png(estado, tamanho = 32) {
  const [r, g, b] = CORES[estado] || CORES.livre;
  const linhas = [];
  const meio = (tamanho - 1) / 2;
  for (let y = 0; y < tamanho; y++) {
    const linha = Buffer.alloc(1 + tamanho * 4);
    for (let x = 0; x < tamanho; x++) {
      const d = Math.hypot(x - meio, y - meio) / (tamanho / 2);
      let px = [0, 0, 0, 0];
      if (d <= 0.46) px = [r, g, b, 255];
      else if (d >= 0.7 && d <= 0.92) px = [255, 230, 203, 255];
      const borda = (lim, dentro) => Math.max(0, Math.min(1, (dentro ? lim - d : d - lim) * tamanho / 2 + 0.5));
      if (d > 0.46 && d < 0.52) px = [r, g, b, Math.round(255 * borda(0.49, true))];
      if (d > 0.66 && d < 0.7) px = [255, 230, 203, Math.round(255 * borda(0.68, false))];
      if (d > 0.92 && d < 0.97) px = [255, 230, 203, Math.round(255 * borda(0.94, true))];
      linha.set(px, 1 + x * 4);
    }
    linhas.push(linha);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(tamanho, 0);
  ihdr.writeUInt32BE(tamanho, 4);
  ihdr.set([8, 6, 0, 0, 0], 8);
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    bloco("IHDR", ihdr),
    bloco("IDAT", zlib.deflateSync(Buffer.concat(linhas))),
    bloco("IEND", Buffer.alloc(0)),
  ]);
}

module.exports = { png };
