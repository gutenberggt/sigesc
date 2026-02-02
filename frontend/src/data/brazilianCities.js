/**
 * Lista de cidades brasileiras para autocomplete
 * Esta é uma lista curada das principais cidades brasileiras
 * Fonte: IBGE
 */

export const BRAZILIAN_CITIES = [
  // Acre
  "Rio Branco - AC", "Cruzeiro do Sul - AC", "Sena Madureira - AC", "Tarauacá - AC", "Feijó - AC",
  // Alagoas
  "Maceió - AL", "Arapiraca - AL", "Rio Largo - AL", "Palmeira dos Índios - AL", "União dos Palmares - AL",
  "Penedo - AL", "São Miguel dos Campos - AL", "Delmiro Gouveia - AL", "Coruripe - AL", "Campo Alegre - AL",
  // Amapá
  "Macapá - AP", "Santana - AP", "Laranjal do Jari - AP", "Oiapoque - AP", "Mazagão - AP",
  // Amazonas
  "Manaus - AM", "Parintins - AM", "Itacoatiara - AM", "Manacapuru - AM", "Coari - AM",
  "Tefé - AM", "Tabatinga - AM", "Maués - AM", "Humaitá - AM", "São Gabriel da Cachoeira - AM",
  // Bahia
  "Salvador - BA", "Feira de Santana - BA", "Vitória da Conquista - BA", "Camaçari - BA", "Itabuna - BA",
  "Juazeiro - BA", "Lauro de Freitas - BA", "Ilhéus - BA", "Jequié - BA", "Teixeira de Freitas - BA",
  "Barreiras - BA", "Alagoinhas - BA", "Porto Seguro - BA", "Simões Filho - BA", "Paulo Afonso - BA",
  "Eunápolis - BA", "Santo Antônio de Jesus - BA", "Valença - BA", "Candeias - BA", "Guanambi - BA",
  // Ceará
  "Fortaleza - CE", "Caucaia - CE", "Juazeiro do Norte - CE", "Maracanaú - CE", "Sobral - CE",
  "Crato - CE", "Itapipoca - CE", "Maranguape - CE", "Iguatu - CE", "Quixadá - CE",
  "Pacatuba - CE", "Aquiraz - CE", "Canindé - CE", "Crateús - CE", "Pacajus - CE",
  // Distrito Federal
  "Brasília - DF", "Ceilândia - DF", "Taguatinga - DF", "Samambaia - DF", "Planaltina - DF",
  "Águas Claras - DF", "Recanto das Emas - DF", "Gama - DF", "Guará - DF", "Santa Maria - DF",
  // Espírito Santo
  "Vitória - ES", "Vila Velha - ES", "Serra - ES", "Cariacica - ES", "Cachoeiro de Itapemirim - ES",
  "Linhares - ES", "São Mateus - ES", "Colatina - ES", "Guarapari - ES", "Aracruz - ES",
  // Goiás
  "Goiânia - GO", "Aparecida de Goiânia - GO", "Anápolis - GO", "Rio Verde - GO", "Luziânia - GO",
  "Águas Lindas de Goiás - GO", "Valparaíso de Goiás - GO", "Trindade - GO", "Formosa - GO", "Novo Gama - GO",
  "Itumbiara - GO", "Senador Canedo - GO", "Catalão - GO", "Jataí - GO", "Planaltina - GO",
  // Maranhão
  "São Luís - MA", "Imperatriz - MA", "São José de Ribamar - MA", "Timon - MA", "Caxias - MA",
  "Codó - MA", "Paço do Lumiar - MA", "Açailândia - MA", "Bacabal - MA", "Balsas - MA",
  "Santa Inês - MA", "Barra do Corda - MA", "Pinheiro - MA", "Chapadinha - MA", "Itapecuru Mirim - MA",
  // Mato Grosso
  "Cuiabá - MT", "Várzea Grande - MT", "Rondonópolis - MT", "Sinop - MT", "Tangará da Serra - MT",
  "Cáceres - MT", "Sorriso - MT", "Lucas do Rio Verde - MT", "Primavera do Leste - MT", "Barra do Garças - MT",
  // Mato Grosso do Sul
  "Campo Grande - MS", "Dourados - MS", "Três Lagoas - MS", "Corumbá - MS", "Ponta Porã - MS",
  "Naviraí - MS", "Nova Andradina - MS", "Aquidauana - MS", "Sidrolândia - MS", "Paranaíba - MS",
  // Minas Gerais
  "Belo Horizonte - MG", "Uberlândia - MG", "Contagem - MG", "Juiz de Fora - MG", "Betim - MG",
  "Montes Claros - MG", "Ribeirão das Neves - MG", "Uberaba - MG", "Governador Valadares - MG", "Ipatinga - MG",
  "Sete Lagoas - MG", "Divinópolis - MG", "Santa Luzia - MG", "Ibirité - MG", "Poços de Caldas - MG",
  "Patos de Minas - MG", "Pouso Alegre - MG", "Teófilo Otoni - MG", "Barbacena - MG", "Sabará - MG",
  "Varginha - MG", "Conselheiro Lafaiete - MG", "Araguari - MG", "Itabira - MG", "Passos - MG",
  "Coronel Fabriciano - MG", "Muriaé - MG", "Ituiutaba - MG", "Araxá - MG", "Lavras - MG",
  // Pará
  "Belém - PA", "Ananindeua - PA", "Santarém - PA", "Marabá - PA", "Castanhal - PA",
  "Parauapebas - PA", "Marituba - PA", "Abaetetuba - PA", "Cametá - PA", "Bragança - PA",
  "Tucuruí - PA", "Altamira - PA", "Barcarena - PA", "Tailândia - PA", "Itaituba - PA",
  // Paraíba
  "João Pessoa - PB", "Campina Grande - PB", "Santa Rita - PB", "Patos - PB", "Bayeux - PB",
  "Sousa - PB", "Cajazeiras - PB", "Cabedelo - PB", "Guarabira - PB", "Sapé - PB",
  // Paraná
  "Curitiba - PR", "Londrina - PR", "Maringá - PR", "Ponta Grossa - PR", "Cascavel - PR",
  "São José dos Pinhais - PR", "Foz do Iguaçu - PR", "Colombo - PR", "Guarapuava - PR", "Paranaguá - PR",
  "Araucária - PR", "Toledo - PR", "Apucarana - PR", "Pinhais - PR", "Campo Largo - PR",
  "Almirante Tamandaré - PR", "Umuarama - PR", "Piraquara - PR", "Cambé - PR", "Arapongas - PR",
  // Pernambuco
  "Recife - PE", "Jaboatão dos Guararapes - PE", "Olinda - PE", "Caruaru - PE", "Petrolina - PE",
  "Paulista - PE", "Cabo de Santo Agostinho - PE", "Camaragibe - PE", "Garanhuns - PE", "Vitória de Santo Antão - PE",
  "Igarassu - PE", "São Lourenço da Mata - PE", "Abreu e Lima - PE", "Serra Talhada - PE", "Araripina - PE",
  // Piauí
  "Teresina - PI", "Parnaíba - PI", "Picos - PI", "Piripiri - PI", "Floriano - PI",
  "Campo Maior - PI", "Barras - PI", "União - PI", "Altos - PI", "Esperantina - PI",
  // Rio de Janeiro
  "Rio de Janeiro - RJ", "São Gonçalo - RJ", "Duque de Caxias - RJ", "Nova Iguaçu - RJ", "Niterói - RJ",
  "Belford Roxo - RJ", "Campos dos Goytacazes - RJ", "São João de Meriti - RJ", "Petrópolis - RJ", "Volta Redonda - RJ",
  "Magé - RJ", "Itaboraí - RJ", "Mesquita - RJ", "Nova Friburgo - RJ", "Barra Mansa - RJ",
  "Macaé - RJ", "Cabo Frio - RJ", "Nilópolis - RJ", "Teresópolis - RJ", "Angra dos Reis - RJ",
  // Rio Grande do Norte
  "Natal - RN", "Mossoró - RN", "Parnamirim - RN", "São Gonçalo do Amarante - RN", "Ceará-Mirim - RN",
  "Macaíba - RN", "Caicó - RN", "Açu - RN", "Currais Novos - RN", "São José de Mipibu - RN",
  // Rio Grande do Sul
  "Porto Alegre - RS", "Caxias do Sul - RS", "Pelotas - RS", "Canoas - RS", "Santa Maria - RS",
  "Gravataí - RS", "Viamão - RS", "Novo Hamburgo - RS", "São Leopoldo - RS", "Rio Grande - RS",
  "Alvorada - RS", "Passo Fundo - RS", "Sapucaia do Sul - RS", "Uruguaiana - RS", "Cachoeirinha - RS",
  "Santa Cruz do Sul - RS", "Bagé - RS", "Bento Gonçalves - RS", "Erechim - RS", "Guaíba - RS",
  // Rondônia
  "Porto Velho - RO", "Ji-Paraná - RO", "Ariquemes - RO", "Vilhena - RO", "Cacoal - RO",
  "Rolim de Moura - RO", "Jaru - RO", "Guajará-Mirim - RO", "Ouro Preto do Oeste - RO", "Buritis - RO",
  // Roraima
  "Boa Vista - RR", "Rorainópolis - RR", "Caracaraí - RR", "Alto Alegre - RR", "Mucajaí - RR",
  // Santa Catarina
  "Joinville - SC", "Florianópolis - SC", "Blumenau - SC", "São José - SC", "Chapecó - SC",
  "Criciúma - SC", "Itajaí - SC", "Lages - SC", "Jaraguá do Sul - SC", "Palhoça - SC",
  "Balneário Camboriú - SC", "Brusque - SC", "Tubarão - SC", "São Bento do Sul - SC", "Caçador - SC",
  "Concórdia - SC", "Camboriú - SC", "Navegantes - SC", "Rio do Sul - SC", "Araranguá - SC",
  // São Paulo
  "São Paulo - SP", "Guarulhos - SP", "Campinas - SP", "São Bernardo do Campo - SP", "Santo André - SP",
  "São José dos Campos - SP", "Osasco - SP", "Ribeirão Preto - SP", "Sorocaba - SP", "Santos - SP",
  "Mauá - SP", "São José do Rio Preto - SP", "Mogi das Cruzes - SP", "Diadema - SP", "Jundiaí - SP",
  "Piracicaba - SP", "Carapicuíba - SP", "Bauru - SP", "Itaquaquecetuba - SP", "São Vicente - SP",
  "Franca - SP", "Praia Grande - SP", "Guarujá - SP", "Taubaté - SP", "Limeira - SP",
  "Suzano - SP", "Taboão da Serra - SP", "Sumaré - SP", "Barueri - SP", "Embu das Artes - SP",
  "São Carlos - SP", "Indaiatuba - SP", "Cotia - SP", "Americana - SP", "Marília - SP",
  "Araraquara - SP", "Jacareí - SP", "Presidente Prudente - SP", "Santa Bárbara d'Oeste - SP", "Rio Claro - SP",
  "Araçatuba - SP", "Hortolândia - SP", "Ferraz de Vasconcelos - SP", "Itapevi - SP", "Francisco Morato - SP",
  "Itapecerica da Serra - SP", "Pindamonhangaba - SP", "Franco da Rocha - SP", "Bragança Paulista - SP", "Itu - SP",
  // Sergipe
  "Aracaju - SE", "Nossa Senhora do Socorro - SE", "Lagarto - SE", "Itabaiana - SE", "São Cristóvão - SE",
  "Estância - SE", "Tobias Barreto - SE", "Itabaianinha - SE", "Simão Dias - SE", "Capela - SE",
  // Tocantins
  "Palmas - TO", "Araguaína - TO", "Gurupi - TO", "Porto Nacional - TO", "Paraíso do Tocantins - TO",
  "Colinas do Tocantins - TO", "Guaraí - TO", "Tocantinópolis - TO", "Dianópolis - TO", "Miracema do Tocantins - TO",
  // Cidades adicionais do Pará (região do Araguaia)
  "Floresta do Araguaia - PA", "Conceição do Araguaia - PA", "Redenção - PA", "Xinguara - PA", "São Félix do Xingu - PA",
  "Ourilândia do Norte - PA", "Tucumã - PA", "Água Azul do Norte - PA", "Cumaru do Norte - PA", "Bannach - PA",
  "Pau D'Arco - PA", "Rio Maria - PA", "Sapucaia - PA", "Piçarra - PA", "São Geraldo do Araguaia - PA"
].sort((a, b) => a.localeCompare(b, 'pt-BR'));

/**
 * Busca cidades que começam com o texto fornecido
 * @param {string} searchText - Texto para buscar (mínimo 3 caracteres)
 * @returns {string[]} Lista de cidades que correspondem à busca
 */
export const searchCities = (searchText) => {
  if (!searchText || searchText.length < 3) return [];
  
  const normalizedSearch = searchText.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  
  return BRAZILIAN_CITIES.filter(city => {
    const normalizedCity = city.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    return normalizedCity.startsWith(normalizedSearch) || 
           normalizedCity.includes(normalizedSearch);
  }).slice(0, 10); // Limita a 10 resultados
};
