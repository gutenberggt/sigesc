import { createContext, useContext } from 'react';

export const GradesContext = createContext(null);

export const useGrades = () => {
  const ctx = useContext(GradesContext);
  if (!ctx) {
    throw new Error('useGrades must be used inside <GradesContext.Provider>');
  }
  return ctx;
};
