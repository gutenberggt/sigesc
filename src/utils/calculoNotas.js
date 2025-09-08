//MÓDULO 2
//Funções utilitárias para cálculo de total, média e recuperação.
export function roundUp1(value) {
  if (value === null || value === undefined || value === "") return "";
  const num = Number(value);
  if (Number.isNaN(num)) return "";
  return Math.ceil(num * 10) / 10;
}

export function fmt1(value) {
  if (value === "" || value === null || value === undefined) return "";
  const v = roundUp1(value);
  return v.toFixed(1);
}

export function aplicarRecuperacoes(B1, B2, R1, B3, B4, R2) {
  let eB1 = B1 ?? 0,
    eB2 = B2 ?? 0,
    eB3 = B3 ?? 0,
    eB4 = B4 ?? 0;
  const r1 = R1 ?? 0,
    r2 = R2 ?? 0;

  if (r1 > 0) {
    if (eB1 < eB2 && r1 > eB1) eB1 = r1;
    else if (eB2 < eB1 && r1 > eB2) eB2 = r1;
    else if (r1 > eB2) eB2 = r1;
  }

  if (r2 > 0) {
    if (eB3 < eB4 && r2 > eB3) eB3 = r2;
    else if (eB4 < eB3 && r2 > eB4) eB4 = r2;
    else if (r2 > eB4) eB4 = r2;
  }

  return [eB1, eB2, eB3, eB4];
}

export function calcularTotais(B1, B2, R1, B3, B4, R2) {
  const [eB1, eB2, eB3, eB4] = aplicarRecuperacoes(B1, B2, R1, B3, B4, R2);
  const total = eB1 * 2 + eB2 * 3 + eB3 * 2 + eB4 * 3;
  const media = total / 10;
  return { total: roundUp1(total), media: roundUp1(media) };
}
