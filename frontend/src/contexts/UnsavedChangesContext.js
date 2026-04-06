import { createContext, useContext, useRef, useCallback } from 'react';

const UnsavedChangesContext = createContext({
  getUnsavedState: () => ({ hasChanges: false, message: '' }),
  setUnsavedState: () => {},
});

export const UnsavedChangesProvider = ({ children }) => {
  const stateRef = useRef({ hasChanges: false, message: '' });

  const getUnsavedState = useCallback(() => stateRef.current, []);
  const setUnsavedState = useCallback((hasChanges, message = '') => {
    stateRef.current = { hasChanges, message };
  }, []);

  return (
    <UnsavedChangesContext.Provider value={{ getUnsavedState, setUnsavedState }}>
      {children}
    </UnsavedChangesContext.Provider>
  );
};

export const useUnsavedChangesContext = () => useContext(UnsavedChangesContext);
