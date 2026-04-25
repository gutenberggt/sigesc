// Silencia console.log / console.debug / console.info em build de produção.
// Mantém console.warn e console.error visíveis (importantes para diagnóstico em campo).
// Importado uma única vez em src/index.js.
if (process.env.NODE_ENV === 'production') {
  const noop = () => {};
  // eslint-disable-next-line no-console
  console.log = noop;
  // eslint-disable-next-line no-console
  console.debug = noop;
  // eslint-disable-next-line no-console
  console.info = noop;
}
