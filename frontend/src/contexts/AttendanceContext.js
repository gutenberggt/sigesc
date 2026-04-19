import { createContext, useContext } from 'react';

export const AttendanceContext = createContext(null);

export const useAttendance = () => {
  const ctx = useContext(AttendanceContext);
  if (!ctx) {
    throw new Error('useAttendance must be used inside <AttendanceContext.Provider>');
  }
  return ctx;
};
