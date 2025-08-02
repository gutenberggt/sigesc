import React, { useState, useEffect, useMemo } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, query, where } from 'firebase/firestore';
import { Calendar, momentLocalizer } from 'react-big-calendar';
import moment from 'moment';
import 'moment/locale/pt-br';
import 'react-big-calendar/lib/css/react-big-calendar.css';

moment.locale('pt-br');
const localizer = momentLocalizer(moment);

const ColoredDateCellWrapper = ({ children, value, events }) => {
  const event = events.find(
    e => moment(e.start).isSame(value, 'day')
  );

  const isToday = moment().isSame(value, 'day');

  let backgroundColor = '';
  let tooltip = '';

  if (event) {
    tooltip = event.title;
    if (event.resource?.type?.includes('FERIADO')) {
      backgroundColor = '#ef4444';
    } else if (event.resource?.type === 'RECESSO') {
      backgroundColor = '#f59e0b';
    } else {
      backgroundColor = '#3498db';
    }
  }

  return (
    <div
      style={{
        backgroundColor,
        width: '100%',
        height: '100%',
        borderRadius: '4px',
        transition: 'background 0.3s',
      }}
    >
      <div
        title={tooltip}
        style={{
          width: '100%',
          height: '100%',
          border: isToday ? '2px solid green' : 'none',
          borderRadius: isToday ? '50%' : '0',
          boxSizing: 'border-box',
        }}
      >
        {children}
      </div>
    </div>
  );
};

const YearView = ({ year, events, eventPropGetter }) => {
  const months = Array.from({ length: 12 }, (_, i) => i);

  return (
    <div className="grid grid-cols-1 sm:grid-cols-1 md:grid-cols-3 gap-4">
      {months.map(month => (
        <div key={month} className="mb-4">
          <h4 className="text-center font-bold text-lg mb-2">
            {moment(new Date(year, month, 1)).format('MMMM')}
          </h4>
          <div style={{ height: 280 }}>
            <Calendar
              localizer={localizer}
              events={events}
              startAccessor="start"
              endAccessor="end"
              views={['month']}
              defaultView="month"
              date={new Date(year, month, 1)}
              toolbar={false}
              eventPropGetter={() => ({ style: { display: 'none' } })}
              components={{
                dateCellWrapper: (props) => (
                  <ColoredDateCellWrapper {...props} events={events} />
                )
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
};

function CalendarioPage() {
  const [events, setEvents] = useState([]);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear().toString());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [view, setView] = useState('month');
  const [navigateDate, setNavigateDate] = useState(new Date());

  const years = useMemo(() => {
    const startYear = 2024;
    const endYear = 2030;
    return Array.from({ length: endYear - startYear + 1 }, (_, i) => (startYear + i).toString());
  }, []);

  useEffect(() => {
    const fetchCalendarData = async () => {
      if (!selectedYear) return;
      setLoading(true);
      setError('');
      try {
        const allEvents = [];
        const eventosQuery = query(collection(db, 'eventos'), where('anoLetivo', '==', selectedYear));
        const eventosSnapshot = await getDocs(eventosQuery);
        eventosSnapshot.forEach(doc => {
          const data = doc.data();
          allEvents.push({
            title: data.descricao,
            start: new Date(`${data.data}T00:00:00`),
            end: new Date(`${data.data}T23:59:59`),
            allDay: true,
            resource: { type: data.tipo },
          });
        });

        setEvents(allEvents);
      } catch (err) {
        console.error("Erro ao buscar dados do calendário:", err);
        setError("Não foi possível carregar os dados do calendário.");
      } finally {
        setLoading(false);
      }
    };
    fetchCalendarData();
  }, [selectedYear]);

  useEffect(() => {
    const newDate = new Date(selectedYear, 0, 1);
    setNavigateDate(newDate);
  }, [selectedYear]);

  const eventStyleGetter = (event) => {
    let backgroundColor = '#3498db';
    if (event.resource?.type?.includes('FERIADO')) {
      backgroundColor = '#ef4444';
    } else if (event.resource?.type === 'RECESSO') {
      backgroundColor = '#f59e0b';
    }
    
	const style = {
	  backgroundColor,
	  borderRadius: '5px',
	  opacity: 0.8,
	  color: 'white',
	  border: '0px',
	  display: 'block',
	  cursor: 'pointer'
	};
	return {
	  style: style,
	  title: event.title // <-- Isso habilita o tooltip padrão do browser
	};
	};

  const messages = {
      allDay: 'Dia Inteiro',
      previous: 'Anterior',
      next: 'Próximo',
      today: 'Hoje',
      month: 'Mês',
      week: 'Semana',
      day: 'Dia',
      agenda: 'Agenda',
      date: 'Data',
      time: 'Hora',
      event: 'Evento',
      noEventsInRange: 'Não há eventos neste período.',
      showMore: total => `+ Ver mais (${total})`
  };

  return (
    <div className="p-6">
      {/* ======================= INÍCIO DA ALTERAÇÃO ======================= */}
      <div className="bg-white p-8 rounded-lg shadow-md max-w-7xl mx-auto flex flex-col min-h-[85vh]">
      {/* ======================== FIM DA ALTERAÇÃO ========================= */}
        <h2 className="text-2xl font-bold mb-4 text-gray-800 flex-shrink-0">Calendário Acadêmico</h2>

        <div className="flex flex-wrap justify-between items-center mb-4 flex-shrink-0">
            <div className="mb-4 md:mb-0">
                <label htmlFor="year-select" className="mr-2 font-semibold">Ano Letivo:</label>
                <select
                    id="year-select"
                    value={selectedYear}
                    onChange={(e) => setSelectedYear(e.target.value)}
                    className="p-2 border rounded-md"
                >
                    {years.map(year => (<option key={year} value={year}>{year}</option>))}
                </select>
            </div>

            <div className="flex space-x-1 border p-1 rounded-md bg-gray-100">
                <button onClick={() => setView('year')} className={`px-3 py-1 text-sm rounded ${view === 'year' ? 'bg-blue-600 text-white' : 'bg-transparent'}`}>Ano</button>
                <button onClick={() => setView('month')} className={`px-3 py-1 text-sm rounded ${view === 'month' ? 'bg-blue-600 text-white' : 'bg-transparent'}`}>Mês</button>
                <button onClick={() => setView('week')} className={`px-3 py-1 text-sm rounded ${view === 'week' ? 'bg-blue-600 text-white' : 'bg-transparent'}`}>Semana</button>
                <button onClick={() => setView('day')} className={`px-3 py-1 text-sm rounded ${view === 'day' ? 'bg-blue-600 text-white' : 'bg-transparent'}`}>Dia</button>
            </div>
        </div>

        {error && <p className="text-red-500 text-center mb-4 flex-shrink-0">{error}</p>}

        {/* ======================= INÍCIO DA ALTERAÇÃO ======================= */}
        <div className="flex-grow">
        {/* ======================== FIM DA ALTERAÇÃO ========================= */}
            {loading ? (
                <p>Carregando calendário...</p>
            ) : (
                <>
                    {view === 'year' ? (
                        <YearView year={parseInt(selectedYear, 10)} events={events} eventPropGetter={eventStyleGetter} />
                    ) : (
                        <Calendar
						  key={selectedYear}
						  date={navigateDate}
						  onNavigate={date => setNavigateDate(date)}
						  localizer={localizer}
						  events={events}
						  startAccessor="start"
						  endAccessor="end"
						  style={{ height: '600px' }} // <-- Altura adequada aqui
						  eventPropGetter={eventStyleGetter}
						  messages={messages}
						  view={view}
						  onView={setView}
						/>

                    )}
                </>
            )}
        </div>
      </div>
    </div>
  );
}

export default CalendarioPage;