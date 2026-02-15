import { useState, useEffect, useMemo } from 'react';
import { Layout } from '@/components/Layout';
import { 
  Calendar as CalendarIcon, 
  ChevronLeft, 
  ChevronRight, 
  Plus,
  Eye,
  Edit,
  Trash2,
  Sun,
  Moon,
  Sunrise,
  Clock,
  AlertCircle,
  CheckCircle,
  XCircle,
  Home
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/Modal';
import { calendarAPI } from '@/services/api';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { ClassScheduleTab } from '@/components/ClassScheduleTab';

// Helper para obter data local no formato YYYY-MM-DD (evita problemas de timezone)
const getLocalDateString = (date = new Date()) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// Tipos de eventos com cores e labels
const EVENT_TYPES = {
  feriado_nacional: { label: 'Feriado Nacional', color: '#EF4444', bg: 'bg-red-100' },
  feriado_estadual: { label: 'Feriado Estadual', color: '#F97316', bg: 'bg-orange-100' },
  feriado_municipal: { label: 'Feriado Municipal', color: '#EAB308', bg: 'bg-yellow-100' },
  sabado_letivo: { label: 'Sábado Letivo', color: '#22C55E', bg: 'bg-green-100' },
  recesso_escolar: { label: 'Recesso Escolar', color: '#3B82F6', bg: 'bg-blue-100' },
  evento_escolar: { label: 'Evento Escolar', color: '#8B5CF6', bg: 'bg-purple-100' },
  outros: { label: 'Outros', color: '#6B7280', bg: 'bg-gray-100' }
};

// Períodos do dia
const PERIODS = {
  integral: { label: 'Integral (Dia todo)', icon: CalendarIcon },
  manha: { label: 'Manhã', icon: Sunrise },
  tarde: { label: 'Tarde', icon: Sun },
  noite: { label: 'Noite', icon: Moon },
  personalizado: { label: 'Horário Personalizado', icon: Clock }
};

// Nomes dos meses
const MONTHS = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
];

// Nomes dos dias da semana
const WEEKDAYS = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
const WEEKDAYS_FULL = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'];

// Helper para formatar data
const formatDate = (dateStr) => {
  if (!dateStr) return '';
  const [year, month, day] = dateStr.split('-');
  return `${day}/${month}/${year}`;
};

// Helper para obter dias do mês
const getDaysInMonth = (year, month) => {
  return new Date(year, month + 1, 0).getDate();
};

// Helper para obter primeiro dia da semana do mês
const getFirstDayOfMonth = (year, month) => {
  return new Date(year, month, 1).getDay();
};

// Componente de Evento
const EventBadge = ({ event, compact = false, onClick }) => {
  const type = EVENT_TYPES[event.event_type] || EVENT_TYPES.outros;
  
  if (compact) {
    return (
      <div 
        className="w-2 h-2 rounded-full cursor-pointer" 
        style={{ backgroundColor: event.color || type.color }}
        title={event.name}
        onClick={() => onClick?.(event)}
      />
    );
  }
  
  return (
    <div 
      className={`text-xs px-2 py-1 rounded truncate cursor-pointer hover:opacity-80 ${event.is_school_day ? 'border-l-4 border-green-500' : ''}`}
      style={{ backgroundColor: event.color || type.color, color: 'white' }}
      title={`${event.name}${event.is_school_day ? ' (Letivo)' : ' (Não Letivo)'}`}
      onClick={() => onClick?.(event)}
    >
      {event.name}
    </div>
  );
};

// Componente de célula do dia
const DayCell = ({ date, events, isToday, isCurrentMonth, onClick, onEventClick, academicYear, periodosBimestrais }) => {
  const dayEvents = events.filter(e => {
    return date >= e.start_date && date <= e.end_date;
  });
  
  // Verifica se é final de semana
  const dateObj = new Date(date + 'T12:00:00');
  const dayOfWeek = dateObj.getDay();
  const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
  
  // Verifica se está dentro dos períodos letivos (usando períodos bimestrais se disponíveis)
  let isInSchoolPeriod = false;
  let bimestreAtual = null;
  
  if (periodosBimestrais && Object.keys(periodosBimestrais).some(k => periodosBimestrais[k])) {
    // Usa os períodos configurados
    for (let i = 1; i <= 4; i++) {
      const inicio = periodosBimestrais[`bimestre_${i}_inicio`];
      const fim = periodosBimestrais[`bimestre_${i}_fim`];
      if (inicio && fim && date >= inicio && date <= fim) {
        isInSchoolPeriod = true;
        bimestreAtual = i;
        break;
      }
    }
  } else {
    // Fallback para períodos padrão
    const year = academicYear || new Date().getFullYear();
    isInSchoolPeriod = (
      (date >= `${year}-02-09` && date <= `${year}-06-30`) ||
      (date >= `${year}-08-03` && date <= `${year}-12-18`)
    );
  }
  
  // Verifica se é início ou fim de bimestre
  let isBimestreStart = false;
  let isBimestreEnd = false;
  let bimestreInfo = null;
  
  if (periodosBimestrais) {
    for (let i = 1; i <= 4; i++) {
      const inicio = periodosBimestrais[`bimestre_${i}_inicio`];
      const fim = periodosBimestrais[`bimestre_${i}_fim`];
      if (date === inicio) {
        isBimestreStart = true;
        bimestreInfo = `Início ${i}º Bim`;
      }
      if (date === fim) {
        isBimestreEnd = true;
        bimestreInfo = `Fim ${i}º Bim`;
      }
    }
  }
  
  // Verifica eventos
  const hasNonSchoolDay = dayEvents.some(e => !e.is_school_day);
  const hasSchoolDay = dayEvents.some(e => e.is_school_day);
  const hasFeriado = dayEvents.some(e => e.event_type?.includes('feriado'));
  const hasRecesso = dayEvents.some(e => e.event_type === 'recesso_escolar');
  
  // Determina se é dia letivo
  // É letivo se: está no período letivo + não é final de semana + não tem feriado/recesso
  const isSchoolDay = isInSchoolPeriod && !isWeekend && !hasFeriado && !hasRecesso && !hasNonSchoolDay;
  
  // Define a cor de fundo
  let bgClass = 'bg-white';
  if (!isCurrentMonth) {
    bgClass = 'bg-gray-50 text-gray-400';
  } else if (hasFeriado) {
    bgClass = 'bg-red-100';
  } else if (hasRecesso) {
    bgClass = 'bg-blue-50';
  } else if (isWeekend && hasSchoolDay) {
    // Sábado letivo - mesma cor dos dias letivos
    bgClass = 'bg-green-100';
  } else if (isWeekend && isInSchoolPeriod) {
    bgClass = 'bg-gray-100';
  } else if (isSchoolDay) {
    // Dia letivo normal (seg-sex) - verde claro
    bgClass = 'bg-green-100';
  } else if (hasSchoolDay) {
    bgClass = 'bg-green-100';
  }
  
  return (
    <div 
      className={`min-h-[80px] p-1 border border-gray-200 cursor-pointer hover:bg-gray-50 transition-colors
        ${bgClass}
        ${isToday ? 'ring-2 ring-blue-500' : ''}
        ${isBimestreStart ? 'border-l-4 border-l-green-500' : ''}
        ${isBimestreEnd ? 'border-r-4 border-r-red-500' : ''}
      `}
      onClick={() => onClick(date)}
    >
      <div className={`text-sm font-medium mb-1 flex items-center justify-between ${isToday ? 'text-blue-600' : ''}`}>
        <span>{parseInt(date.split('-')[2])}</span>
        <div className="flex items-center gap-1">
          {isBimestreStart && (
            <span className="text-[9px] px-1 bg-green-500 text-white rounded" title={bimestreInfo}>▶</span>
          )}
          {isBimestreEnd && (
            <span className="text-[9px] px-1 bg-red-500 text-white rounded" title={bimestreInfo}>◀</span>
          )}
          {isCurrentMonth && isInSchoolPeriod && !isWeekend && !hasFeriado && !hasRecesso && (
            <span className="w-2 h-2 rounded-full bg-green-500" title="Dia Letivo"></span>
          )}
        </div>
      </div>
      {bimestreInfo && isCurrentMonth && (
        <div className={`text-[8px] mb-1 px-1 py-0.5 rounded text-center truncate ${isBimestreStart ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
          {bimestreInfo}
        </div>
      )}
      <div className="space-y-1">
        {dayEvents
          .filter(event => event.name !== 'Sábado' && event.name !== 'Domingo')
          .slice(0, 3)
          .map((event, idx) => (
            <EventBadge 
              key={event.id || idx} 
              event={event} 
              compact={dayEvents.length > 2}
              onClick={onEventClick}
            />
          ))}
        {dayEvents.filter(event => event.name !== 'Sábado' && event.name !== 'Domingo').length > 3 && (
          <div className="text-xs text-gray-500">+{dayEvents.filter(event => event.name !== 'Sábado' && event.name !== 'Domingo').length - 3} mais</div>
        )}
      </div>
    </div>
  );
};

// Vista Anual
const AnnualView = ({ year, events, onDayClick, onEventClick, periodosBimestrais }) => {
  // Função para determinar se uma data está dentro do período letivo
  const isDateInSchoolPeriod = (dateStr) => {
    if (periodosBimestrais && Object.keys(periodosBimestrais).some(k => periodosBimestrais[k])) {
      for (let i = 1; i <= 4; i++) {
        const inicio = periodosBimestrais[`bimestre_${i}_inicio`];
        const fim = periodosBimestrais[`bimestre_${i}_fim`];
        if (inicio && fim && dateStr >= inicio && dateStr <= fim) {
          return true;
        }
      }
      return false;
    }
    // Fallback para períodos padrão se não configurados
    return (
      (dateStr >= `${year}-02-09` && dateStr <= `${year}-06-30`) ||
      (dateStr >= `${year}-08-03` && dateStr <= `${year}-12-18`)
    );
  };

  // Função para calcular dias letivos de um mês
  const calcularDiasLetivosMes = (monthIndex) => {
    const daysInMonth = getDaysInMonth(year, monthIndex);
    let diasLetivos = 0;
    
    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${year}-${String(monthIndex + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const dayEvents = events.filter(e => dateStr >= e.start_date && dateStr <= e.end_date);
      
      const dateObj = new Date(dateStr + 'T12:00:00');
      const dayOfWeek = dateObj.getDay();
      const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
      const isSaturday = dayOfWeek === 6;
      
      const hasFeriado = dayEvents.some(e => e.event_type?.includes('feriado'));
      const hasRecesso = dayEvents.some(e => e.event_type === 'recesso_escolar');
      const hasSabadoLetivo = dayEvents.some(e => e.event_type === 'sabado_letivo' || (e.is_school_day && isSaturday));
      const hasNonSchoolDay = dayEvents.some(e => !e.is_school_day);
      
      const isInSchoolPeriod = isDateInSchoolPeriod(dateStr);
      
      // É dia letivo se: está no período + não é fds (ou é sábado letivo) + não tem feriado/recesso
      const isSchoolDay = isInSchoolPeriod && !hasFeriado && !hasRecesso && !hasNonSchoolDay && 
        (!isWeekend || hasSabadoLetivo);
      
      if (isSchoolDay) {
        diasLetivos++;
      }
    }
    
    return diasLetivos;
  };

  return (
    <div className="grid grid-cols-3 md:grid-cols-4 gap-4">
      {MONTHS.map((month, monthIndex) => {
        const daysInMonth = getDaysInMonth(year, monthIndex);
        const firstDay = getFirstDayOfMonth(year, monthIndex);
        const diasLetivosMes = calcularDiasLetivosMes(monthIndex);
        const days = [];
        
        // Dias vazios antes do primeiro dia
        for (let i = 0; i < firstDay; i++) {
          days.push(<div key={`empty-${i}`} className="text-center text-xs p-1" />);
        }
        
        // Dias do mês
        for (let day = 1; day <= daysInMonth; day++) {
          const dateStr = `${year}-${String(monthIndex + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
          const dayEvents = events.filter(e => dateStr >= e.start_date && dateStr <= e.end_date);
          const isToday = dateStr === getLocalDateString();
          
          // Verifica tipo de dia
          const dateObj = new Date(dateStr + 'T12:00:00');
          const dayOfWeek = dateObj.getDay();
          const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
          const isSaturday = dayOfWeek === 6;
          
          // Verifica eventos
          const hasFeriado = dayEvents.some(e => e.event_type?.includes('feriado'));
          const hasRecesso = dayEvents.some(e => e.event_type === 'recesso_escolar');
          const hasSabadoLetivo = dayEvents.some(e => e.event_type === 'sabado_letivo' || (e.is_school_day && isSaturday));
          const hasNonSchoolDay = dayEvents.some(e => !e.is_school_day);
          
          // Verifica se está no período letivo
          const isInSchoolPeriod = isDateInSchoolPeriod(dateStr);
          
          // Determina se é dia letivo (seg-sex, dentro do período, sem feriado/recesso)
          const isSchoolDay = isInSchoolPeriod && !isWeekend && !hasFeriado && !hasRecesso && !hasNonSchoolDay;
          
          // Define a cor de fundo baseado na hierarquia
          let bgClass = '';
          let textClass = '';
          
          if (hasFeriado) {
            // Feriado - vermelho claro
            bgClass = 'bg-red-100';
            textClass = 'text-red-700';
          } else if (hasRecesso) {
            // Recesso - azul claro
            bgClass = 'bg-blue-50';
            textClass = 'text-blue-700';
          } else if (hasSabadoLetivo) {
            // Sábado letivo - mesma cor dos dias letivos
            bgClass = 'bg-green-100';
            textClass = 'text-green-700';
          } else if (isWeekend && isInSchoolPeriod) {
            // Fim de semana normal (dentro do período letivo) - cinza
            bgClass = 'bg-gray-100';
            textClass = 'text-gray-500';
          } else if (isWeekend) {
            // Fim de semana fora do período letivo
            bgClass = 'bg-gray-100';
            textClass = 'text-gray-400';
          } else if (isSchoolDay) {
            // Dia letivo (seg-sex) - verde claro
            bgClass = 'bg-green-100';
            textClass = 'text-green-700';
          }
          
          const title = dayEvents.length > 0 
            ? dayEvents.map(e => e.name).join(', ')
            : isSchoolDay 
              ? 'Dia Letivo' 
              : isWeekend 
                ? (isSaturday ? 'Sábado' : 'Domingo')
                : '';
          
          days.push(
            <div 
              key={day}
              className={`text-center text-xs p-1 cursor-pointer hover:opacity-80 rounded
                ${isToday ? 'ring-1 ring-blue-500 font-bold' : ''}
                ${bgClass}
                ${textClass}
              `}
              title={title}
              onClick={() => onDayClick(dateStr)}
            >
              {day}
            </div>
          );
        }
        
        return (
          <div key={month} className="bg-white rounded-lg shadow-sm border p-3">
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-semibold text-sm text-gray-700">{month}</h4>
              <span className="text-xs text-green-600 font-medium">{diasLetivosMes} dias letivos</span>
            </div>
            <div className="grid grid-cols-7 gap-0.5 text-xs text-gray-500 mb-1">
              {WEEKDAYS.map(d => <div key={d} className="text-center">{d[0]}</div>)}
            </div>
            <div className="grid grid-cols-7 gap-0.5">
              {days}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// Vista Mensal
const MonthlyView = ({ year, month, events, onDayClick, onEventClick, periodosBimestrais }) => {
  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfMonth(year, month);
  const today = getLocalDateString();
  
  // Função para determinar se uma data está dentro do período letivo
  const isDateInSchoolPeriod = (dateStr) => {
    if (periodosBimestrais && Object.keys(periodosBimestrais).some(k => periodosBimestrais[k])) {
      for (let i = 1; i <= 4; i++) {
        const inicio = periodosBimestrais[`bimestre_${i}_inicio`];
        const fim = periodosBimestrais[`bimestre_${i}_fim`];
        if (inicio && fim && dateStr >= inicio && dateStr <= fim) {
          return true;
        }
      }
      return false;
    }
    // Fallback para períodos padrão se não configurados
    return (
      (dateStr >= `${year}-02-09` && dateStr <= `${year}-06-30`) ||
      (dateStr >= `${year}-08-03` && dateStr <= `${year}-12-18`)
    );
  };

  // Calcular dias letivos do mês atual
  const calcularDiasLetivosMes = () => {
    let diasLetivos = 0;
    
    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const dayEvents = events.filter(e => dateStr >= e.start_date && dateStr <= e.end_date);
      
      const dateObj = new Date(dateStr + 'T12:00:00');
      const dayOfWeek = dateObj.getDay();
      const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
      const isSaturday = dayOfWeek === 6;
      
      const hasFeriado = dayEvents.some(e => e.event_type?.includes('feriado'));
      const hasRecesso = dayEvents.some(e => e.event_type === 'recesso_escolar');
      const hasSabadoLetivo = dayEvents.some(e => e.event_type === 'sabado_letivo' || (e.is_school_day && isSaturday));
      const hasNonSchoolDay = dayEvents.some(e => !e.is_school_day);
      
      const isInSchoolPeriod = isDateInSchoolPeriod(dateStr);
      
      // É dia letivo se: está no período + não é fds (ou é sábado letivo) + não tem feriado/recesso
      const isSchoolDay = isInSchoolPeriod && !hasFeriado && !hasRecesso && !hasNonSchoolDay && 
        (!isWeekend || hasSabadoLetivo);
      
      if (isSchoolDay) {
        diasLetivos++;
      }
    }
    
    return diasLetivos;
  };

  const diasLetivosMes = calcularDiasLetivosMes();
  
  // Dias do mês anterior
  const prevMonthDays = getDaysInMonth(year, month - 1);
  const prevMonth = month === 0 ? 11 : month - 1;
  const prevYear = month === 0 ? year - 1 : year;
  
  // Dias do próximo mês
  const nextMonth = month === 11 ? 0 : month + 1;
  const nextYear = month === 11 ? year + 1 : year;
  
  const cells = [];
  
  // Dias do mês anterior
  for (let i = firstDay - 1; i >= 0; i--) {
    const day = prevMonthDays - i;
    const dateStr = `${prevYear}-${String(prevMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    cells.push(
      <DayCell 
        key={`prev-${day}`}
        date={dateStr}
        events={events}
        isToday={dateStr === today}
        isCurrentMonth={false}
        onClick={onDayClick}
        onEventClick={onEventClick}
        periodosBimestrais={periodosBimestrais}
      />
    );
  }
  
  // Dias do mês atual
  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    cells.push(
      <DayCell 
        key={day}
        date={dateStr}
        events={events}
        isToday={dateStr === today}
        isCurrentMonth={true}
        onClick={onDayClick}
        onEventClick={onEventClick}
        periodosBimestrais={periodosBimestrais}
      />
    );
  }
  
  // Dias do próximo mês
  const remainingCells = 42 - cells.length;
  for (let day = 1; day <= remainingCells; day++) {
    const dateStr = `${nextYear}-${String(nextMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    cells.push(
      <DayCell 
        key={`next-${day}`}
        date={dateStr}
        events={events}
        isToday={dateStr === today}
        isCurrentMonth={false}
        onClick={onDayClick}
        onEventClick={onEventClick}
        periodosBimestrais={periodosBimestrais}
      />
    );
  }
  
  return (
    <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
      {/* Header com dias letivos */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b">
        <span className="text-sm font-medium text-gray-700">{MONTHS[month]} {year}</span>
        <span className="text-sm text-green-600 font-medium">{diasLetivosMes} dias letivos</span>
      </div>
      <div className="grid grid-cols-7 bg-gray-100">
        {WEEKDAYS.map(day => (
          <div key={day} className="p-2 text-center text-sm font-medium text-gray-600 border-b">
            {day}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {cells}
      </div>
    </div>
  );
};

// Vista Semanal
const WeeklyView = ({ startDate, events, onDayClick, onEventClick }) => {
  // Formata data de hoje sem problemas de timezone
  const today = getLocalDateString();
  
  // Gera os 7 dias da semana (Domingo a Sábado)
  const weekDays = [];
  const start = new Date(startDate + 'T12:00:00'); // Usa meio-dia para evitar problemas de timezone
  
  for (let i = 0; i < 7; i++) {
    const date = new Date(start);
    date.setDate(start.getDate() + i);
    
    // Formata a data manualmente para evitar problemas de timezone
    const year = date.getFullYear();
    const month = date.getMonth();
    const dayOfMonth = date.getDate();
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(dayOfMonth).padStart(2, '0')}`;
    
    const dayEvents = events.filter(e => dateStr >= e.start_date && dateStr <= e.end_date);
    
    weekDays.push({
      date: dateStr,
      dayName: WEEKDAYS_FULL[date.getDay()],
      day: dayOfMonth,
      month: MONTHS[month],
      events: dayEvents,
      isToday: dateStr === today
    });
  }
  
  return (
    <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
      <div className="grid grid-cols-7">
        {weekDays.map(day => (
          <div 
            key={day.date}
            className={`border-r last:border-r-0 min-h-[400px] ${day.isToday ? 'bg-blue-50' : ''}`}
          >
            <div 
              className={`p-2 text-center border-b cursor-pointer hover:bg-gray-50
                ${day.isToday ? 'bg-blue-100' : 'bg-gray-50'}
              `}
              onClick={() => onDayClick(day.date)}
            >
              <div className="text-xs text-gray-500">{day.dayName}</div>
              <div className={`text-lg font-semibold ${day.isToday ? 'text-blue-600' : ''}`}>
                {day.day}
              </div>
              <div className="text-xs text-gray-400">{day.month}</div>
            </div>
            <div className="p-2 space-y-2">
              {day.events
                .filter(event => event.name !== 'Sábado' && event.name !== 'Domingo')
                .map((event, idx) => (
                  <EventBadge key={event.id || idx} event={event} onClick={onEventClick} />
                ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Vista Diária
const DailyView = ({ date, events, onEventClick }) => {
  const allDayEvents = events.filter(e => date >= e.start_date && date <= e.end_date);
  // Filtra para não exibir "Sábado" e "Domingo"
  const dayEvents = allDayEvents.filter(e => e.name !== 'Sábado' && e.name !== 'Domingo');
  const dateObj = new Date(date + 'T12:00:00');
  
  // Horas do dia
  const hours = [];
  for (let h = 6; h <= 22; h++) {
    hours.push(h);
  }
  
  return (
    <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
      <div className="p-4 bg-gray-50 border-b">
        <div className="text-center">
          <div className="text-sm text-gray-500">{WEEKDAYS_FULL[dateObj.getDay()]}</div>
          <div className="text-3xl font-bold">{dateObj.getDate()}</div>
          <div className="text-sm text-gray-500">{MONTHS[dateObj.getMonth()]} {dateObj.getFullYear()}</div>
        </div>
      </div>
      
      {/* Eventos do dia */}
      {dayEvents.length > 0 && (
        <div className="p-4 border-b">
          <h4 className="text-sm font-semibold text-gray-700 mb-2">Eventos do Dia</h4>
          <div className="space-y-2">
            {dayEvents.map((event, idx) => {
              const type = EVENT_TYPES[event.event_type] || EVENT_TYPES.outros;
              const period = PERIODS[event.period] || PERIODS.integral;
              
              return (
                <div 
                  key={event.id || idx}
                  className={`p-3 rounded-lg cursor-pointer hover:opacity-90 ${type.bg}`}
                  style={{ borderLeft: `4px solid ${event.color || type.color}` }}
                  onClick={() => onEventClick(event)}
                >
                  <div className="flex items-center justify-between">
                    <div className="font-medium">{event.name}</div>
                    <div className="flex items-center gap-2">
                      {event.is_school_day ? (
                        <span className="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded">Letivo</span>
                      ) : (
                        <span className="text-xs px-2 py-0.5 bg-red-100 text-red-700 rounded">Não Letivo</span>
                      )}
                    </div>
                  </div>
                  <div className="text-sm text-gray-600 mt-1">{type.label}</div>
                  <div className="text-xs text-gray-500 flex items-center gap-1 mt-1">
                    <period.icon size={12} />
                    {period.label}
                    {event.period === 'personalizado' && event.start_time && event.end_time && (
                      <span className="ml-1">({event.start_time} - {event.end_time})</span>
                    )}
                  </div>
                  {event.description && (
                    <div className="text-sm text-gray-500 mt-2">{event.description}</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
      
      {/* Timeline do dia */}
      <div className="p-4">
        <div className="space-y-0">
          {hours.map(hour => (
            <div key={hour} className="flex border-t border-gray-100 min-h-[40px]">
              <div className="w-16 text-xs text-gray-400 py-2 text-right pr-2">
                {hour}:00
              </div>
              <div className="flex-1 py-1">
                {dayEvents
                  .filter(e => {
                    if (e.period === 'integral') return true;
                    if (e.period === 'manha' && hour >= 7 && hour < 12) return true;
                    if (e.period === 'tarde' && hour >= 13 && hour < 18) return true;
                    if (e.period === 'noite' && hour >= 18 && hour < 22) return true;
                    if (e.period === 'personalizado' && e.start_time && e.end_time) {
                      const startHour = parseInt(e.start_time.split(':')[0]);
                      const endHour = parseInt(e.end_time.split(':')[0]);
                      return hour >= startHour && hour < endHour;
                    }
                    return false;
                  })
                  .map((event, idx) => (
                    <div 
                      key={`${event.id}-${hour}-${idx}`}
                      className="text-xs px-2 py-1 rounded mb-1"
                      style={{ backgroundColor: event.color || EVENT_TYPES[event.event_type]?.color, color: 'white' }}
                    >
                      {event.name}
                    </div>
                  ))
                }
              </div>
            </div>
          ))}
        </div>
      </div>
      
      {dayEvents.length === 0 && (
        <div className="p-8 text-center text-gray-500">
          <CalendarIcon size={48} className="mx-auto mb-2 opacity-30" />
          <p>Nenhum evento neste dia</p>
        </div>
      )}
    </div>
  );
};

// Componente Principal
export const Calendar = () => {
  const { user } = useAuth();
  const [mainTab, setMainTab] = useState('calendario'); // 'calendario' ou 'horario'
  const [view, setView] = useState('monthly'); // annual, monthly, weekly, daily
  const [currentDate, setCurrentDate] = useState(new Date());
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [showEventModal, setShowEventModal] = useState(false);
  const [showPeriodosModal, setShowPeriodosModal] = useState(false);
  const [calendarioLetivo, setCalendarioLetivo] = useState(null);
  const [diasLetivosCalculados, setDiasLetivosCalculados] = useState(null);
  const [savingPeriodos, setSavingPeriodos] = useState(false);
  const [anoSelecionadoPeriodos, setAnoSelecionadoPeriodos] = useState(new Date().getFullYear());
  const navigateTo = useNavigate();
  
  const currentYear = currentDate.getFullYear();
  const currentMonth = currentDate.getMonth();
  
  // Verificar se usuário pode editar datas limite (apenas admin e secretario)
  const canEditDataLimite = user?.role && ['admin', 'secretario'].includes(user.role);
  
  // Estado para os períodos bimestrais
  const [periodos, setPeriodos] = useState({
    bimestre_1_inicio: '',
    bimestre_1_fim: '',
    bimestre_1_data_limite: '',
    bimestre_2_inicio: '',
    bimestre_2_fim: '',
    bimestre_2_data_limite: '',
    bimestre_3_inicio: '',
    bimestre_3_fim: '',
    bimestre_3_data_limite: '',
    bimestre_4_inicio: '',
    bimestre_4_fim: '',
    bimestre_4_data_limite: '',
    recesso_inicio: '',
    recesso_fim: ''
  });
  
  // Carrega eventos
  useEffect(() => {
    loadEvents();
    loadCalendarioLetivo();
  }, [currentYear]);
  
  const loadEvents = async () => {
    setLoading(true);
    try {
      const data = await calendarAPI.getEvents({ academic_year: currentYear });
      setEvents(data);
      // Recarregar dias letivos quando eventos mudam
      loadDiasLetivos();
    } catch (error) {
      console.error('Erro ao carregar eventos:', error);
    } finally {
      setLoading(false);
    }
  };
  
  const loadDiasLetivos = async (ano = currentYear) => {
    try {
      const data = await calendarAPI.getDiasLetivos(ano);
      setDiasLetivosCalculados(data);
    } catch (error) {
      console.error('Erro ao calcular dias letivos:', error);
    }
  };
  
  const loadCalendarioLetivo = async (ano = currentYear) => {
    try {
      const data = await calendarAPI.getCalendarioLetivo(ano);
      setCalendarioLetivo(data);
      setPeriodos({
        bimestre_1_inicio: data.bimestre_1_inicio || '',
        bimestre_1_fim: data.bimestre_1_fim || '',
        bimestre_1_data_limite: data.bimestre_1_data_limite || '',
        bimestre_2_inicio: data.bimestre_2_inicio || '',
        bimestre_2_fim: data.bimestre_2_fim || '',
        bimestre_2_data_limite: data.bimestre_2_data_limite || '',
        bimestre_3_inicio: data.bimestre_3_inicio || '',
        bimestre_3_fim: data.bimestre_3_fim || '',
        bimestre_3_data_limite: data.bimestre_3_data_limite || '',
        bimestre_4_inicio: data.bimestre_4_inicio || '',
        bimestre_4_fim: data.bimestre_4_fim || '',
        bimestre_4_data_limite: data.bimestre_4_data_limite || '',
        recesso_inicio: data.recesso_inicio || '',
        recesso_fim: data.recesso_fim || ''
      });
      // Carregar dias letivos calculados
      loadDiasLetivos(ano);
    } catch (error) {
      console.error('Erro ao carregar calendário letivo:', error);
      // Se não encontrou, limpar os campos
      setPeriodos({
        bimestre_1_inicio: '',
        bimestre_1_fim: '',
        bimestre_1_data_limite: '',
        bimestre_2_inicio: '',
        bimestre_2_fim: '',
        bimestre_2_data_limite: '',
        bimestre_3_inicio: '',
        bimestre_3_fim: '',
        bimestre_3_data_limite: '',
        bimestre_4_inicio: '',
        bimestre_4_fim: '',
        bimestre_4_data_limite: '',
        recesso_inicio: '',
        recesso_fim: ''
      });
    }
  };
  
  const handleSavePeriodos = async () => {
    setSavingPeriodos(true);
    try {
      await calendarAPI.updateCalendarioLetivo(anoSelecionadoPeriodos, periodos);
      setShowPeriodosModal(false);
      // Se o ano selecionado for o ano atual, recarrega
      if (anoSelecionadoPeriodos === currentYear) {
        await loadCalendarioLetivo(currentYear);
        await loadDiasLetivos(currentYear);
      }
    } catch (error) {
      console.error('Erro ao salvar períodos:', error);
      alert('Erro ao salvar períodos bimestrais');
    } finally {
      setSavingPeriodos(false);
    }
  };
  
  // Função para carregar períodos quando muda o ano no modal
  const handleAnoSelecionadoChange = async (ano) => {
    setAnoSelecionadoPeriodos(ano);
    await loadCalendarioLetivo(ano);
  };
  
  // Configurar Períodos Bimestrais - Exclusivo ao administrador
  const canEditPeriodos = user?.role === 'admin' || user?.role === 'admin_teste';
  
  // Navegação
  const navigate = (direction) => {
    const newDate = new Date(currentDate);
    
    switch (view) {
      case 'annual':
        newDate.setFullYear(newDate.getFullYear() + direction);
        break;
      case 'monthly':
        newDate.setMonth(newDate.getMonth() + direction);
        break;
      case 'weekly':
        newDate.setDate(newDate.getDate() + (direction * 7));
        break;
      case 'daily':
        newDate.setDate(newDate.getDate() + direction);
        break;
    }
    
    setCurrentDate(newDate);
  };
  
  const goToToday = () => {
    setCurrentDate(new Date());
  };
  
  // Título da navegação
  const getNavigationTitle = () => {
    switch (view) {
      case 'annual':
        return currentYear;
      case 'monthly':
        return `${MONTHS[currentMonth]} ${currentYear}`;
      case 'weekly':
        const weekStart = new Date(currentDate);
        weekStart.setDate(weekStart.getDate() - weekStart.getDay());
        const weekEnd = new Date(weekStart);
        weekEnd.setDate(weekEnd.getDate() + 6);
        return `${weekStart.getDate()} ${MONTHS[weekStart.getMonth()]} - ${weekEnd.getDate()} ${MONTHS[weekEnd.getMonth()]} ${currentYear}`;
      case 'daily':
        return `${currentDate.getDate()} de ${MONTHS[currentMonth]} de ${currentYear}`;
      default:
        return '';
    }
  };
  
  // Início da semana para vista semanal (Domingo)
  const getWeekStart = () => {
    const date = new Date(currentDate);
    const day = date.getDay(); // 0 = Domingo, 6 = Sábado
    date.setDate(date.getDate() - day);
    // Formata manualmente para evitar problemas de timezone
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const dayOfMonth = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${dayOfMonth}`;
  };
  
  // Handlers
  const handleDayClick = (date) => {
    setSelectedDate(date);
    if (view !== 'daily') {
      setCurrentDate(new Date(date + 'T12:00:00'));
      setView('daily');
    }
  };
  
  const handleEventClick = (event) => {
    setSelectedEvent(event);
    setShowEventModal(true);
  };
  
  return (
    <Layout>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigateTo(user?.role === 'professor' ? '/professor' : '/dashboard')}
              className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <Home size={18} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
                <CalendarIcon className="text-blue-600" />
                Calendário Letivo
              </h1>
              <p className="text-gray-600 text-sm">Visualize feriados, eventos e dias letivos</p>
            </div>
          </div>
          
          <div className="flex gap-2">
            {(user?.role === 'admin' || user?.role === 'admin_teste') && mainTab === 'calendario' && (
              <>
                <Button variant="outline" onClick={() => {
                  setAnoSelecionadoPeriodos(currentYear);
                  loadCalendarioLetivo(currentYear);
                  setShowPeriodosModal(true);
                }}>
                  <Clock size={18} className="mr-2" />
                  Períodos Bimestrais
                </Button>
                <Button onClick={() => navigateTo('/admin/events')}>
                  <Plus size={18} className="mr-2" />
                  Gerenciar Eventos
                </Button>
              </>
            )}
          </div>
        </div>
        
        {/* Abas Principais: Calendário / Horário de Aulas */}
        <div className="bg-white rounded-lg shadow-sm border">
          <div className="flex border-b">
            <button
              onClick={() => setMainTab('calendario')}
              className={`flex-1 px-6 py-3 text-sm font-medium transition-colors
                ${mainTab === 'calendario' 
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50' 
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'}`}
            >
              <CalendarIcon size={18} className="inline-block mr-2 -mt-0.5" />
              Calendário Letivo
            </button>
            <button
              onClick={() => setMainTab('horario')}
              className={`flex-1 px-6 py-3 text-sm font-medium transition-colors
                ${mainTab === 'horario' 
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50' 
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'}`}
            >
              <Clock size={18} className="inline-block mr-2 -mt-0.5" />
              Horário de Aulas
            </button>
          </div>
        </div>
        
        {/* Conteúdo da aba Calendário */}
        {mainTab === 'calendario' && (
          <>
        {/* Controles */}
        <div className="bg-white rounded-lg shadow-sm border p-4">
          <div className="flex flex-col sm:flex-row justify-between items-center gap-4">
            {/* Seletor de vista */}
            <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
              {[
                { id: 'annual', label: 'Anual' },
                { id: 'monthly', label: 'Mensal' },
                { id: 'weekly', label: 'Semanal' },
                { id: 'daily', label: 'Diário' }
              ].map(v => (
                <button
                  key={v.id}
                  className={`px-4 py-2 text-sm rounded-md transition-colors ${
                    view === v.id ? 'bg-white shadow text-blue-600 font-medium' : 'text-gray-600 hover:bg-gray-200'
                  }`}
                  onClick={() => setView(v.id)}
                >
                  {v.label}
                </button>
              ))}
            </div>
            
            {/* Navegação */}
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
                <ChevronLeft size={18} />
              </Button>
              <div className="min-w-[200px] text-center font-medium">
                {getNavigationTitle()}
              </div>
              <Button variant="outline" size="sm" onClick={() => navigate(1)}>
                <ChevronRight size={18} />
              </Button>
              <Button variant="outline" size="sm" onClick={goToToday}>
                Hoje
              </Button>
            </div>
          </div>
        </div>
        
        {/* Legenda */}
        <div className="bg-white rounded-lg shadow-sm border p-4">
          <div className="flex flex-wrap gap-4 text-sm">
            {Object.entries(EVENT_TYPES).map(([key, value]) => (
              <div key={key} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded" style={{ backgroundColor: value.color }} />
                <span>{value.label}</span>
              </div>
            ))}
            <div className="flex items-center gap-2 ml-4 pl-4 border-l">
              <CheckCircle size={14} className="text-green-500" />
              <span>Letivo</span>
            </div>
            <div className="flex items-center gap-2">
              <XCircle size={14} className="text-red-500" />
              <span>Não Letivo</span>
            </div>
            <div className="flex items-center gap-2 ml-4 pl-4 border-l">
              <span className="text-[9px] px-1.5 py-0.5 bg-green-500 text-white rounded">▶</span>
              <span>Início Bim.</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[9px] px-1.5 py-0.5 bg-red-500 text-white rounded">◀</span>
              <span>Fim Bim.</span>
            </div>
          </div>
        </div>
        
        {/* Info dos Períodos Configurados */}
        {calendarioLetivo && calendarioLetivo.bimestre_1_inicio && (
          <div className="bg-white rounded-lg shadow-sm border p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium text-gray-700">Períodos Bimestrais Configurados</h4>
              <div className="flex items-center gap-2 bg-indigo-100 px-3 py-1 rounded-full">
                <span className="text-xs text-indigo-600 font-medium">Dias Letivos Anuais:</span>
                <span className="text-sm font-bold text-indigo-800">
                  {diasLetivosCalculados?.total_dias_letivos || 0}
                </span>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div className="p-2 bg-blue-50 rounded-lg">
                <div className="flex justify-between items-center mb-1">
                  <span className="font-medium text-blue-800">1º Bimestre</span>
                  <span className="text-xs bg-blue-200 text-blue-800 px-2 py-0.5 rounded-full font-medium">
                    {diasLetivosCalculados?.bimestre_1_dias_letivos || 0} dias
                  </span>
                </div>
                <div className="text-blue-600 text-xs">
                  {calendarioLetivo.bimestre_1_inicio && new Date(calendarioLetivo.bimestre_1_inicio + 'T12:00:00').toLocaleDateString('pt-BR')} a {calendarioLetivo.bimestre_1_fim && new Date(calendarioLetivo.bimestre_1_fim + 'T12:00:00').toLocaleDateString('pt-BR')}
                </div>
              </div>
              <div className="p-2 bg-green-50 rounded-lg">
                <div className="flex justify-between items-center mb-1">
                  <span className="font-medium text-green-800">2º Bimestre</span>
                  <span className="text-xs bg-green-200 text-green-800 px-2 py-0.5 rounded-full font-medium">
                    {diasLetivosCalculados?.bimestre_2_dias_letivos || 0} dias
                  </span>
                </div>
                <div className="text-green-600 text-xs">
                  {calendarioLetivo.bimestre_2_inicio && new Date(calendarioLetivo.bimestre_2_inicio + 'T12:00:00').toLocaleDateString('pt-BR')} a {calendarioLetivo.bimestre_2_fim && new Date(calendarioLetivo.bimestre_2_fim + 'T12:00:00').toLocaleDateString('pt-BR')}
                </div>
              </div>
              <div className="p-2 bg-yellow-50 rounded-lg">
                <div className="flex justify-between items-center mb-1">
                  <span className="font-medium text-yellow-800">3º Bimestre</span>
                  <span className="text-xs bg-yellow-200 text-yellow-800 px-2 py-0.5 rounded-full font-medium">
                    {diasLetivosCalculados?.bimestre_3_dias_letivos || 0} dias
                  </span>
                </div>
                <div className="text-yellow-600 text-xs">
                  {calendarioLetivo.bimestre_3_inicio && new Date(calendarioLetivo.bimestre_3_inicio + 'T12:00:00').toLocaleDateString('pt-BR')} a {calendarioLetivo.bimestre_3_fim && new Date(calendarioLetivo.bimestre_3_fim + 'T12:00:00').toLocaleDateString('pt-BR')}
                </div>
              </div>
              <div className="p-2 bg-purple-50 rounded-lg">
                <div className="flex justify-between items-center mb-1">
                  <span className="font-medium text-purple-800">4º Bimestre</span>
                  <span className="text-xs bg-purple-200 text-purple-800 px-2 py-0.5 rounded-full font-medium">
                    {diasLetivosCalculados?.bimestre_4_dias_letivos || 0} dias
                  </span>
                </div>
                <div className="text-purple-600 text-xs">
                  {calendarioLetivo.bimestre_4_inicio && new Date(calendarioLetivo.bimestre_4_inicio + 'T12:00:00').toLocaleDateString('pt-BR')} a {calendarioLetivo.bimestre_4_fim && new Date(calendarioLetivo.bimestre_4_fim + 'T12:00:00').toLocaleDateString('pt-BR')}
                </div>
              </div>
            </div>
          </div>
        )}
        
        {/* Calendário */}
        {loading ? (
          <div className="flex justify-center items-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : (
          <>
            {view === 'annual' && (
              <AnnualView 
                year={currentYear} 
                events={events}
                onDayClick={handleDayClick}
                onEventClick={handleEventClick}
                periodosBimestrais={calendarioLetivo}
              />
            )}
            {view === 'monthly' && (
              <MonthlyView 
                year={currentYear}
                month={currentMonth}
                events={events}
                onDayClick={handleDayClick}
                onEventClick={handleEventClick}
                periodosBimestrais={calendarioLetivo}
              />
            )}
            {view === 'weekly' && (
              <WeeklyView 
                startDate={getWeekStart()}
                events={events}
                onDayClick={handleDayClick}
                onEventClick={handleEventClick}
              />
            )}
            {view === 'daily' && (
              <DailyView 
                date={currentDate.toISOString().split('T')[0]}
                events={events}
                onEventClick={handleEventClick}
              />
            )}
          </>
        )}
          </>
        )}
        
        {/* Conteúdo da aba Horário de Aulas */}
        {mainTab === 'horario' && (
          <ClassScheduleTab academicYear={currentYear} />
        )}
        
        {/* Modal de detalhes do evento */}
        <Modal
          isOpen={showEventModal}
          onClose={() => {
            setShowEventModal(false);
            setSelectedEvent(null);
          }}
          title="Detalhes do Evento"
        >
          {selectedEvent && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div 
                  className="w-4 h-4 rounded"
                  style={{ backgroundColor: selectedEvent.color || EVENT_TYPES[selectedEvent.event_type]?.color }}
                />
                <h3 className="text-lg font-semibold">{selectedEvent.name}</h3>
              </div>
              
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Tipo:</span>
                  <p className="font-medium">{EVENT_TYPES[selectedEvent.event_type]?.label}</p>
                </div>
                <div>
                  <span className="text-gray-500">Dia Letivo:</span>
                  <p className={`font-medium ${selectedEvent.is_school_day ? 'text-green-600' : 'text-red-600'}`}>
                    {selectedEvent.is_school_day ? 'Sim' : 'Não'}
                  </p>
                </div>
                <div>
                  <span className="text-gray-500">Data Início:</span>
                  <p className="font-medium">{formatDate(selectedEvent.start_date)}</p>
                </div>
                <div>
                  <span className="text-gray-500">Data Fim:</span>
                  <p className="font-medium">{formatDate(selectedEvent.end_date)}</p>
                </div>
                <div>
                  <span className="text-gray-500">Período:</span>
                  <p className="font-medium">{PERIODS[selectedEvent.period]?.label}</p>
                </div>
                {selectedEvent.period === 'personalizado' && (
                  <div>
                    <span className="text-gray-500">Horário:</span>
                    <p className="font-medium">{selectedEvent.start_time} - {selectedEvent.end_time}</p>
                  </div>
                )}
              </div>
              
              {selectedEvent.description && (
                <div>
                  <span className="text-gray-500 text-sm">Descrição:</span>
                  <p className="mt-1">{selectedEvent.description}</p>
                </div>
              )}
              
              <div className="flex gap-2 pt-4 border-t">
                <Button 
                  variant="outline" 
                  className="flex-1"
                  onClick={() => {
                    setShowEventModal(false);
                    window.location.href = `/admin/events?edit=${selectedEvent.id}`;
                  }}
                >
                  <Edit size={16} className="mr-2" />
                  Editar
                </Button>
                <Button 
                  variant="outline"
                  onClick={() => setShowEventModal(false)}
                >
                  Fechar
                </Button>
              </div>
            </div>
          )}
        </Modal>
        
        {/* Modal de Períodos Bimestrais */}
        <Modal
          isOpen={showPeriodosModal}
          onClose={() => setShowPeriodosModal(false)}
          title="Configurar Períodos Bimestrais"
          size="lg"
        >
          <div className="space-y-6">
            {/* Seletor de Ano */}
            <div className="flex items-center gap-4">
              <label className="text-sm font-medium text-gray-700">Ano Letivo:</label>
              <select
                value={anoSelecionadoPeriodos}
                onChange={(e) => handleAnoSelecionadoChange(parseInt(e.target.value))}
                className="px-3 py-2 border rounded-md text-sm font-medium"
              >
                {[2025, 2026, 2027, 2028, 2029, 2030].map(ano => (
                  <option key={ano} value={ano}>{ano}</option>
                ))}
              </select>
            </div>
            
            <p className="text-sm text-gray-600">
              Defina as datas de início, fim e limite de edição de cada bimestre.
            </p>
            
            {/* 1º Bimestre */}
            <div className="border rounded-lg p-4 bg-blue-50">
              <h4 className="font-medium text-blue-800 mb-3">1º Bimestre</h4>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Início</label>
                  <input
                    type="date"
                    value={periodos.bimestre_1_inicio}
                    onChange={(e) => setPeriodos({...periodos, bimestre_1_inicio: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Fim</label>
                  <input
                    type="date"
                    value={periodos.bimestre_1_fim}
                    onChange={(e) => setPeriodos({...periodos, bimestre_1_fim: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Limite Edição</label>
                  <input
                    type="date"
                    value={periodos.bimestre_1_data_limite}
                    onChange={(e) => setPeriodos({...periodos, bimestre_1_data_limite: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                    disabled={!canEditDataLimite}
                    title={!canEditDataLimite ? "Apenas Admin ou Secretário podem editar" : ""}
                  />
                </div>
              </div>
            </div>
            
            {/* 2º Bimestre */}
            <div className="border rounded-lg p-4 bg-green-50">
              <h4 className="font-medium text-green-800 mb-3">2º Bimestre</h4>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Início</label>
                  <input
                    type="date"
                    value={periodos.bimestre_2_inicio}
                    onChange={(e) => setPeriodos({...periodos, bimestre_2_inicio: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Fim</label>
                  <input
                    type="date"
                    value={periodos.bimestre_2_fim}
                    onChange={(e) => setPeriodos({...periodos, bimestre_2_fim: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Limite Edição</label>
                  <input
                    type="date"
                    value={periodos.bimestre_2_data_limite}
                    onChange={(e) => setPeriodos({...periodos, bimestre_2_data_limite: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                    disabled={!canEditDataLimite}
                    title={!canEditDataLimite ? "Apenas Admin ou Secretário podem editar" : ""}
                  />
                </div>
              </div>
            </div>
            
            {/* Recesso/Férias */}
            <div className="border rounded-lg p-4 bg-gray-50">
              <h4 className="font-medium text-gray-800 mb-3">Recesso/Férias (entre semestres)</h4>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Início</label>
                  <input
                    type="date"
                    value={periodos.recesso_inicio}
                    onChange={(e) => setPeriodos({...periodos, recesso_inicio: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Fim</label>
                  <input
                    type="date"
                    value={periodos.recesso_fim}
                    onChange={(e) => setPeriodos({...periodos, recesso_fim: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                  />
                </div>
              </div>
            </div>
            
            {/* 3º Bimestre */}
            <div className="border rounded-lg p-4 bg-yellow-50">
              <h4 className="font-medium text-yellow-800 mb-3">3º Bimestre</h4>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Início</label>
                  <input
                    type="date"
                    value={periodos.bimestre_3_inicio}
                    onChange={(e) => setPeriodos({...periodos, bimestre_3_inicio: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Fim</label>
                  <input
                    type="date"
                    value={periodos.bimestre_3_fim}
                    onChange={(e) => setPeriodos({...periodos, bimestre_3_fim: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Limite Edição</label>
                  <input
                    type="date"
                    value={periodos.bimestre_3_data_limite}
                    onChange={(e) => setPeriodos({...periodos, bimestre_3_data_limite: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                    disabled={!canEditDataLimite}
                    title={!canEditDataLimite ? "Apenas Admin ou Secretário podem editar" : ""}
                  />
                </div>
              </div>
            </div>
            
            {/* 4º Bimestre */}
            <div className="border rounded-lg p-4 bg-purple-50">
              <h4 className="font-medium text-purple-800 mb-3">4º Bimestre</h4>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Início</label>
                  <input
                    type="date"
                    value={periodos.bimestre_4_inicio}
                    onChange={(e) => setPeriodos({...periodos, bimestre_4_inicio: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Fim</label>
                  <input
                    type="date"
                    value={periodos.bimestre_4_fim}
                    onChange={(e) => setPeriodos({...periodos, bimestre_4_fim: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Data Limite Edição</label>
                  <input
                    type="date"
                    value={periodos.bimestre_4_data_limite}
                    onChange={(e) => setPeriodos({...periodos, bimestre_4_data_limite: e.target.value})}
                    className="w-full px-3 py-2 border rounded-md"
                    disabled={!canEditDataLimite}
                    title={!canEditDataLimite ? "Apenas Admin ou Secretário podem editar" : ""}
                  />
                </div>
              </div>
            </div>
            
            {/* Aviso sobre data limite */}
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <p className="text-xs text-amber-700">
                <strong>Data Limite de Edição:</strong> Após esta data, apenas Administrador, Secretário ou Coordenador poderão editar notas, frequência e objetos do conhecimento do bimestre.
                {!canEditDataLimite && <span className="block mt-1 text-red-600">Você não tem permissão para alterar as datas limite.</span>}
              </p>
            </div>
            
            {/* Botões */}
            <div className="flex gap-2 pt-4 border-t">
              <Button 
                variant="outline" 
                className="flex-1"
                onClick={() => setShowPeriodosModal(false)}
              >
                Cancelar
              </Button>
              <Button 
                className="flex-1"
                onClick={handleSavePeriodos}
                disabled={savingPeriodos}
              >
                {savingPeriodos ? 'Salvando...' : 'Salvar Períodos'}
              </Button>
            </div>
          </div>
        </Modal>
      </div>
    </Layout>
  );
};

export default Calendar;
