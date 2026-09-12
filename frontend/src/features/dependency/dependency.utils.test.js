import { seriesMatches, seriesTokens } from './dependency.utils';

describe('dependency series canonicalization', () => {
  test('normalizes case and ordinal variants', () => {
    expect(seriesMatches('6º ANO', '6º Ano')).toBe(true);
    expect(seriesMatches('6° ano', '6º ANO')).toBe(true);
    expect(seriesMatches('6 ANO', '6º ANO')).toBe(true);
  });

  test('matches a selected series inside a multiseries component scope', () => {
    expect(seriesMatches('6º/7º/9º Ano', '6º ANO')).toBe(true);
    expect(seriesMatches('6º/7º/9º Ano', '8º ANO')).toBe(false);
  });

  test('keeps EJA stages distinct from regular years', () => {
    expect(Array.from(seriesTokens('3ª ETAPA'))).toEqual(['eja:3']);
    expect(seriesMatches('3ª ETAPA', '3º ANO')).toBe(false);
  });
});
